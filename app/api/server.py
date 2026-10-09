"""API HTTP (FastAPI) + hosting del frontend compilato (web/dist).

Avvio:  python -m app  (oppure: uvicorn app.api.server:app --port 8765)
Tutte le API richiedono una sessione valida (vedi app/auth.py), tranne login e stato della sessione.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import COOKIE_NAME, SESSION_TTL_S, AuthError, AuthService
from app.config import DEFAULT_MODELS, PROVIDERS, REASONING_LEVELS, ROOT, mask_key, save_settings, settings
from app.llm.client import get_ledger, get_prices, has_remote
from app.llm.usage import STAGE_LABELS
from app.pipeline.llm_schemas import Assignment
from app.schemas import PersonContent
from app.service.runs import RunManager, RunOptions, to_json

app = FastAPI(title="GarAI", version="2.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
runs = RunManager()
auth = AuthService()

PUBLIC_API = {"/api/auth/login", "/api/auth/me", "/api/auth/logout"}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _is_https(request: Request) -> bool:
    # dietro un proxy (es. Cloud Run) lo schema originale arriva in X-Forwarded-Proto
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _same_origin(request: Request) -> bool:
    """Difesa CSRF (oltre a SameSite=Strict): le richieste che modificano dati devono venire da questa origine."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return True  # client non-browser (CLI, test): nessun cookie di terze parti in gioco
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlsplit(origin).netloc == host


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        if request.method in UNSAFE and not _same_origin(request):
            return JSONResponse({"detail": "Origine della richiesta non consentita."}, status_code=403)
        if path not in PUBLIC_API:
            sess = auth.session(request.cookies.get(COOKIE_NAME))
            if sess is None:
                return JSONResponse({"detail": "Accesso richiesto."}, status_code=401)
            request.state.user = sess.user
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_TTL_S, httponly=True, samesite="strict", secure=_is_https(request), path="/",
    )


class LoginBody(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    try:
        token = auth.login(body.username, body.password, ip)
    except AuthError as e:
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        return JSONResponse({"detail": e.message, "retry_after": e.retry_after}, status_code=e.status, headers=headers)
    _set_session_cookie(response, request, token)
    sess = auth.session(token)
    return {"user": sess.user, "initial_password": sess.initial_password}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    sess = auth.session(request.cookies.get(COOKIE_NAME))
    if sess is None:
        return JSONResponse({"detail": "Accesso richiesto."}, status_code=401)
    return {"user": sess.user, "initial_password": sess.initial_password, "expires": sess.expires}


class PasswordBody(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


@app.post("/api/auth/password")
def change_password(body: PasswordBody, request: Request, response: Response):
    try:
        token = auth.change_password(request.state.user, body.current, body.new)
    except AuthError as e:
        return JSONResponse({"detail": e.message}, status_code=e.status)
    _set_session_cookie(response, request, token)
    return {"ok": True}

ALLOWED_DOCS = {".docx", ".pdf"}
MAX_UPLOAD_MB = 40


@app.exception_handler(KeyError)
async def _not_found(_: Request, e: KeyError):
    return JSONResponse({"detail": f"Non trovato: {e.args[0] if e.args else ''}"}, status_code=404)


@app.exception_handler(ValueError)
async def _bad_request(_: Request, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(RuntimeError)
async def _conflict(_: Request, e: RuntimeError):
    return JSONResponse({"detail": str(e)}, status_code=409)


# ============================================================================ stato e impostazioni
def _renderer_name() -> str:
    import os

    from app.render.powerpoint import available

    forced = os.environ.get("RENDERER", "").lower()
    if forced:
        return forced
    return "powerpoint" if available() else "libreoffice / stima"


@app.get("/api/status")
def status():
    prov = settings.resolved_provider()
    return {
        "provider": prov,
        "configured": has_remote(),
        "models": {t: settings.model_for(prov, t) for t in ("strong", "fast")} if prov in PROVIDERS else {},
        "renderer": _renderer_name(),
        "version": app.version,
    }


def _settings_view() -> dict:
    return {
        "provider": settings.provider,
        "resolved_provider": settings.resolved_provider(),
        "keys": {p: {"set": bool(settings.api_key(p)), "masked": mask_key(settings.api_key(p))} for p in PROVIDERS},
        "models": settings.models,
        "default_models": DEFAULT_MODELS,
        "reasoning": settings.reasoning,
        "reasoning_levels": list(REASONING_LEVELS),
        "run_budget_usd": settings.run_budget_usd,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "max_experiences": settings.max_experiences,
        "max_fit_iterations": settings.max_fit_iterations,
    }


class SettingsPatch(BaseModel):
    provider: str | None = None
    api_keys: dict[str, str] | None = Field(default=None, description="'' cancella la chiave salvata")
    models: dict[str, dict[str, str]] | None = None
    reasoning: dict[str, str] | None = None
    run_budget_usd: float | None = Field(default=None, ge=0)
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    max_experiences: int | None = Field(default=None, ge=1, le=12)
    max_fit_iterations: int | None = Field(default=None, ge=1, le=6)


@app.get("/api/settings")
def get_settings():
    return _settings_view()


@app.put("/api/settings")
def put_settings(patch: SettingsPatch):
    data = patch.model_dump(exclude_none=True)
    if "provider" in data and data["provider"] not in (*PROVIDERS, "auto", "none"):
        raise ValueError(f"Provider non valido: {data['provider']}")
    save_settings(data)
    return _settings_view()


class TestRequest(BaseModel):
    provider: str | None = None


@app.post("/api/settings/test")
def test_provider(req: TestRequest):
    from app.llm.providers import ping

    prov = req.provider or settings.resolved_provider()
    if prov not in PROVIDERS:
        raise ValueError("Seleziona un provider.")
    if not settings.api_key(prov):
        raise ValueError(f"Manca la API key per {prov}.")
    try:
        return {"ok": True, "provider": prov, "tiers": ping(prov, settings)}
    except Exception as e:  # noqa: BLE001 - riportiamo l'errore del provider alla UI
        return {"ok": False, "provider": prov, "error": f"{type(e).__name__}: {e}"[:600]}


# ============================================================================ listino prezzi
@app.get("/api/pricing")
def pricing():
    pb = get_prices()
    today = date.today()
    out = []
    for model, entry in sorted(pb.catalog().items()):
        p = pb.price(model, today)
        out.append({"model": model, **entry, "current": p.__dict__ if p else None})
    return out


class PriceEntry(BaseModel):
    provider: str = "custom"
    label: str | None = None
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float | None = Field(default=None, ge=0)
    cache_write: float | None = Field(default=None, ge=0)


@app.put("/api/pricing/{model}")
def set_price(model: str, e: PriceEntry):
    tier = {"from": "2000-01-01", "input": e.input, "output": e.output}
    if e.cache_read is not None:
        tier["cache_read"] = e.cache_read
    if e.cache_write is not None:
        tier["cache_write"] = e.cache_write
    get_prices().set_override(model, {"provider": e.provider, "label": e.label or model, "tiers": [tier], "verified": False})
    return pricing()


@app.delete("/api/pricing/{model}")
def reset_price(model: str):
    get_prices().set_override(model, None)
    return pricing()


# ============================================================================ costi
def _zone(tz: str | None):
    """Fuso orario del browser (es. 'Europe/Rome'): i giorni dei costi sono quelli dell'utente, non UTC."""
    from zoneinfo import ZoneInfo

    try:
        return ZoneInfo(tz) if tz else timezone.utc
    except Exception:
        return timezone.utc


@app.get("/api/costs/summary")
def costs_summary(days: int = 30, tz: str | None = None):
    led = get_ledger()
    zone = _zone(tz)
    today = datetime.now(zone).date()
    first_day = today - timedelta(days=max(days, 1) - 1) if days > 0 else None
    # inizio del primo giorno locale, espresso in UTC come i timestamp del registro
    start = (
        datetime.combine(first_day, datetime.min.time(), zone).astimezone(timezone.utc).isoformat(timespec="seconds")
        if first_day else None
    )
    by_day, by_day_model = led.daily(start=start, tz=zone)
    by_run = led.group("run", start=start)
    titles = {r.id: r.title for r in runs.list()}
    for r in by_run:
        r["title"] = titles.get(r["key"], "(eliminato)" if r["key"] else "Fuori da un run")
    by_stage = led.group("stage", start=start)
    for r in by_stage:
        r["label"] = STAGE_LABELS.get(r["key"], r["key"])
    month = led.month_cost()
    done_runs = [r for r in runs.list() if r.result]
    n_cv = sum(len(r.cv_files) for r in done_runs if not start or r.created_at >= start)
    totals = led.totals(start=start)
    return {
        "days": days,
        "start": first_day.isoformat() if first_day else None,
        "today": today.isoformat(),
        "totals": totals,
        "by_day": by_day,
        "by_day_model": by_day_model,
        "by_model": led.group("model", start=start),
        "by_stage": by_stage,
        "by_run": sorted(by_run, key=lambda r: r["cost_usd"], reverse=True),
        "month_to_date": month,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "run_budget_usd": settings.run_budget_usd,
        "avg_cost_per_cv": (totals["cost_usd"] / n_cv) if n_cv else None,
        "cvs_processed": n_cv,
    }


@app.get("/api/costs/calls")
def costs_calls(run_id: str | None = None, limit: int = 200):
    rows = get_ledger().calls(run_id=run_id, limit=min(limit, 2000))
    for r in rows:
        r["stage_label"] = STAGE_LABELS.get(r["stage"], r["stage"])
    return rows


# ============================================================================ run
def _run_view(run_id: str) -> dict:
    st = runs.get(run_id)
    data = to_json(st)
    data["cost"] = runs.cost(run_id)
    data["event_seq"] = runs.last_seq(run_id)
    data["output_file"] = st.output_file()  # il client apre lo stream SSE da qui (niente duplicati)
    return data


@app.get("/api/runs")
def list_runs():
    led = get_ledger()
    costs = {r["key"]: r for r in led.group("run")}
    return [r.summary(costs.get(r.id)) for r in runs.list()]


async def _read_upload(f: UploadFile, allowed: set[str]) -> tuple[str, bytes]:
    name = Path(f.filename or "file").name
    if Path(name).suffix.lower() not in allowed:
        raise ValueError(f"Formato non supportato per '{name}': ammessi {', '.join(sorted(allowed))}")
    data = await f.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"'{name}' supera {MAX_UPLOAD_MB} MB")
    return name, data


@app.post("/api/runs")
async def create_run(
    bando: Annotated[UploadFile, File()],
    cvs: Annotated[list[UploadFile], File()],
    template: Annotated[UploadFile | None, File()] = None,
    visual_critic: Annotated[bool, Form()] = False,
    hide_companies: Annotated[bool, Form()] = False,
    output_name: Annotated[str, Form(max_length=200)] = "",
    title: Annotated[str, Form(max_length=300)] = "",
):
    b = await _read_upload(bando, ALLOWED_DOCS)
    cv_files = [await _read_upload(f, ALLOWED_DOCS) for f in cvs]
    tpl = await _read_upload(template, {".pptx"}) if template is not None and template.filename else None
    if not has_remote():
        raise ValueError("Nessun provider LLM configurato: inserisci una API key in Impostazioni.")
    from app.service.runs import clean_output_name

    opts = RunOptions(visual_critic=visual_critic, hide_companies=hide_companies, output_name=clean_output_name(output_name))
    st = runs.create(b, cv_files, tpl, opts, title=title)
    return _run_view(st.id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _run_view(run_id)


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    runs.delete(run_id)
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    """Server-Sent Events: log di avanzamento, chiamate LLM (con costo) e cambi di stato, in tempo reale."""
    runs.get(run_id)
    last = int(request.headers.get("last-event-id") or request.query_params.get("since") or 0)

    async def stream():
        nonlocal last
        yield "retry: 2000\n\n"
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            evs = runs.events_since(run_id, last)
            for e in evs:
                last = e["seq"]
                yield f"id: {e['seq']}\nevent: {e['type']}\ndata: {json.dumps(e['data'], ensure_ascii=False)}\n\n"
            idle = 0 if evs else idle + 1
            if idle and idle % 50 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/runs/{run_id}/analyze")
def reanalyze(run_id: str):
    runs.reanalyze(run_id)
    return _run_view(run_id)


class AssignmentsBody(BaseModel):
    assignments: dict[str, Assignment] = Field(default_factory=dict)
    names: dict[str, str | None] | None = Field(default=None, description="nome file CV -> nome e cognome ('' = assente)")
    details: dict[str, dict] | None = Field(
        default=None, description="nome file CV -> {location, email, phone, current_role, instructions, excluded}"
    )
    guidance: str | None = Field(default=None, description="Indicazioni per la scrittura valide per tutti i candidati.")


@app.put("/api/runs/{run_id}/assignments")
def put_assignments(run_id: str, body: AssignmentsBody):
    runs.set_assignments(run_id, body.assignments, body.names, body.details, body.guidance)
    return _run_view(run_id)


@app.get("/api/runs/{run_id}/estimate")
def get_estimate(run_id: str, visual_critic: bool | None = None):
    return runs.estimate(run_id, visual_critic)


class GenerateBody(BaseModel):
    visual_critic: bool | None = None
    hide_companies: bool | None = None


class OptionsBody(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    visual_critic: bool | None = None
    hide_companies: bool | None = None
    output_name: str | None = Field(default=None, max_length=200)


@app.put("/api/runs/{run_id}/options")
def put_options(run_id: str, body: OptionsBody):
    runs.set_options(run_id, body.visual_critic, body.hide_companies, body.output_name, body.title)
    return _run_view(run_id)


@app.post("/api/runs/{run_id}/generate")
def generate(run_id: str, body: GenerateBody):
    if body.hide_companies is not None:
        runs.set_options(run_id, hide_companies=body.hide_companies)
    runs.generate(run_id, body.visual_critic)
    return _run_view(run_id)


@app.put("/api/runs/{run_id}/people/{source_file}")
def update_person(run_id: str, source_file: str, content: PersonContent):
    runs.update_person(run_id, source_file, content)
    return _run_view(run_id)


@app.post("/api/runs/{run_id}/rebuild")
def rebuild(run_id: str):
    runs.rebuild(run_id)
    return _run_view(run_id)


@app.get("/api/runs/{run_id}/files/{path:path}")
def run_file(run_id: str, path: str, download: bool = False):
    base = runs.run_dir(run_id).resolve()
    f = (base / path).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404, "File non trovato")
    name = f.name
    if download and f.suffix == ".pptx":
        name = runs.get(run_id).output_file()
    return FileResponse(f, filename=name if download else None,
                        headers={"Cache-Control": "no-cache"})


# ============================================================================ frontend
DIST = ROOT / "web" / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    f = (DIST / full_path).resolve()
    if full_path and DIST.resolve() in f.parents and f.is_file():
        return FileResponse(f)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "Frontend non compilato: esegui 'npm install && npm run build' in web/"}, status_code=503)
