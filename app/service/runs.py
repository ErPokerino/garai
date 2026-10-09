"""Gestione dei run (una "pratica": bando + CV -> presentazione): stato persistente, job in background, eventi.

Ogni run vive in `data/runs/<id>/` con `state.json`, i file caricati (`in/`) e gli output (`out/`).
Lo stato sopravvive al riavvio del server; i job in corso al momento dello spegnimento vengono marcati come interrotti.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.ingestion.loader import load_document
from app.llm.base import BudgetExceeded, LLMUnavailable
from app.llm.client import build_client, get_ledger
from app.pipeline.llm_schemas import Assignment
from app.pipeline.run import CVItem, Pipeline
from app.schemas import BandoSpec, CVCanonical, ExperienceBlock, GenerationReport, PersonContent, TemplateSpec
from app.template.spec import load_spec, template_path

from .estimate import estimate_generation

# intervallo di avanzamento complessivo (0..1) coperto da ciascuno stadio, per fase
STAGE_SPAN = {
    "template": (0.0, 0.05), "bando": (0.05, 0.3), "cv": (0.3, 0.75), "match": (0.75, 0.95),
    "write": (0.0, 0.6), "fit": (0.6, 0.85), "render": (0.85, 0.95), "critic": (0.95, 0.99), "done": (1.0, 1.0),
}

Status = Literal["queued", "analyzing", "review", "generating", "done", "error", "interrupted"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LogEntry(BaseModel):
    ts: str
    stage: str
    msg: str
    level: str = "info"


class RunOptions(BaseModel):
    visual_critic: bool = False
    hide_companies: bool = False  # mai nomi di aziende/clienti nelle slide: solo il settore
    output_name: str = ""  # nome del file PPTX scaricato (vuoto = derivato dal titolo del bando)


_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_output_name(name: str) -> str:
    """Nome di file valido su Windows/macOS/Linux, senza estensione; vuoto se non utilizzabile."""
    name = _BAD_CHARS.sub(" ", name or "")
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if name.lower().endswith(".pptx"):
        name = name[:-5].rstrip(". ")
    return name[:120]


class CandidateEdits(BaseModel):
    """Interventi del bid manager su un candidato prima della generazione."""

    instructions: str = ""  # indicazioni per la scrittura (es. cosa mettere in evidenza)
    current_role: str | None = None  # ruolo attuale da riportare cosi' com'e' sulla slide
    excluded: bool = False  # candidato escluso dalla presentazione


class RunResultInfo(BaseModel):
    pptx: str
    report_md: str
    report_json: str
    slides: list[str] = Field(default_factory=list)
    report: GenerationReport
    generated_at: str
    duration_s: float = 0
    edited: bool = False  # True se ricostruito da contenuti modificati a mano
    pending_edits: bool = False  # modifiche salvate ma non ancora applicate al deck


class RunState(BaseModel):
    id: str
    created_at: str
    updated_at: str
    title: str = ""
    status: Status = "queued"
    stage: str = ""
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    options: RunOptions = Field(default_factory=RunOptions)
    provider: str = ""
    models: dict[str, str] = Field(default_factory=dict)
    bando_file: str = ""
    cv_files: list[str] = Field(default_factory=list)
    template_file: str | None = None
    bando: BandoSpec | None = None
    cvs: list[CVCanonical] = Field(default_factory=list)
    assignments: dict[str, Assignment] = Field(default_factory=dict)
    candidates: dict[str, CandidateEdits] = Field(default_factory=dict)
    guidance: str = ""  # indicazioni valide per tutti i candidati
    result: RunResultInfo | None = None
    log: list[LogEntry] = Field(default_factory=list)

    def output_file(self) -> str:
        """Nome del PPTX scaricato: quello scelto dall'utente, altrimenti derivato dal titolo del bando."""
        name = clean_output_name(self.options.output_name)
        if not name:
            stem = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in self.title)[:60].strip() or "CV"
            name = f"{stem} - CV"
        return name + ".pptx"

    def summary(self, cost: dict | None = None) -> dict:
        return {
            "id": self.id, "title": self.title, "status": self.status, "created_at": self.created_at,
            "updated_at": self.updated_at, "n_cvs": len(self.cv_files), "provider": self.provider,
            "language": self.bando.language if self.bando else None,
            "has_result": self.result is not None, "cost_usd": (cost or {}).get("cost_usd", 0.0),
            "calls": (cost or {}).get("calls", 0),
        }


class RunManager:
    def __init__(self, base_dir: Path | None = None):
        self.base = Path(base_dir or settings.data_dir / "runs")
        self.base.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, RunState] = {}
        self._events: dict[str, list[dict]] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="run")
        self._render_lock = threading.Lock()  # PowerPoint (COM) e' una risorsa unica: una generazione alla volta
        self._load_all()

    # ------------------------------------------------------------------ persistenza
    def _dir(self, run_id: str) -> Path:
        return self.base / run_id

    def _load_all(self) -> None:
        for f in self.base.glob("*/state.json"):
            try:
                st = RunState.model_validate_json(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - uno stato corrotto non deve impedire l'avvio
                continue
            if st.status in ("queued", "analyzing", "generating"):
                st.status = "interrupted"
                st.error = "Elaborazione interrotta dal riavvio del server."
            self._runs[st.id] = st
            self._events[st.id] = []

    def _save(self, st: RunState) -> None:
        with self._lock:  # i callback di progresso arrivano da piu' thread
            st.updated_at = _now()
            d = self._dir(st.id)
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / "state.json.tmp"
            tmp.write_text(st.model_dump_json(indent=1), encoding="utf-8")
            tmp.replace(d / "state.json")

    # ------------------------------------------------------------------ eventi (SSE)
    def _emit(self, run_id: str, kind: str, data: dict) -> None:
        with self._lock:
            evs = self._events.setdefault(run_id, [])
            evs.append({"seq": len(evs) + 1, "type": kind, "data": data})
            if len(evs) > 2000:  # tieni la coda limitata: il client recupera lo stato completo via GET
                del evs[: len(evs) - 2000]

    def last_seq(self, run_id: str) -> int:
        with self._lock:
            evs = self._events.get(run_id) or []
            return evs[-1]["seq"] if evs else 0

    def events_since(self, run_id: str, seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self._events.get(run_id, []) if e["seq"] > seq]

    def _log(self, st: RunState, stage: str, msg: str, level: str = "info", progress: float | None = None) -> None:
        entry = LogEntry(ts=_now(), stage=stage, msg=msg, level=level)
        with self._lock:
            st.log.append(entry)
            st.stage, st.message = stage, msg
            if progress is not None:
                st.progress = progress
        self._emit(st.id, "log", {**entry.model_dump(), "progress": st.progress, "status": st.status})

    # ------------------------------------------------------------------ query
    def get(self, run_id: str) -> RunState:
        st = self._runs.get(run_id)
        if st is None:
            raise KeyError(run_id)
        return st

    def list(self) -> list[RunState]:
        return sorted(self._runs.values(), key=lambda s: s.created_at, reverse=True)

    def run_dir(self, run_id: str) -> Path:
        self.get(run_id)
        return self._dir(run_id)

    def delete(self, run_id: str) -> None:
        st = self.get(run_id)
        if st.status in ("analyzing", "generating"):
            raise RuntimeError("Il run e' in elaborazione: attendi il termine prima di eliminarlo.")
        with self._lock:
            self._runs.pop(run_id, None)
            self._events.pop(run_id, None)
        shutil.rmtree(self._dir(run_id), ignore_errors=True)

    # ------------------------------------------------------------------ pipeline
    def _client(self, st: RunState):
        def on_call(row: dict) -> None:
            self._emit(st.id, "llm_call", {k: row[k] for k in (
                "stage", "task", "model", "input_tokens", "output_tokens", "thinking_tokens", "cost_usd",
                "local_cache_hit", "latency_ms")})

        return build_client(run_id=st.id, on_call=on_call)

    def _spec(self, st: RunState, llm) -> TemplateSpec:
        d = self._dir(st.id)
        custom = d / "template" / "spec.json"
        if custom.exists() and st.template_file:
            from app.template.normalize import normalize_spec

            # spec gia' proposto: si ricontrolla (anche quelli salvati da versioni precedenti dell'app)
            spec, _ = normalize_spec(load_spec(custom), d / "in" / st.template_file)
            return spec
        if st.template_file:
            p = d / "in" / st.template_file
            default_sha = hashlib.sha1(template_path(load_spec()).read_bytes()).hexdigest()
            if hashlib.sha1(p.read_bytes()).hexdigest() != default_sha:
                return self._propose_spec(st, llm, p)
        return load_spec()

    def _propose_spec(self, st: RunState, llm, tpl: Path) -> TemplateSpec:
        """Template diverso da quello Abstract: l'LLM con visione ne descrive gli spazi, poi lo spec viene corretto e provato."""
        from app.render.estimate import get_renderer
        from app.template.analyze_llm import propose_spec
        from app.template.deck import build_deck, make_meter
        from app.template.spec import dump_spec

        self._log(st, "template", "Analisi del template della gara (AI con visione)")
        d = self._dir(st.id) / "template"
        renderer = get_renderer(make_meter(load_spec()))
        try:
            imgs = renderer.render(tpl, d / "ref")
        finally:
            renderer.close()
        spec, notes = propose_spec(llm, tpl, imgs)
        for n in notes:
            self._log(st, "template", n, level="warn")
        fillable = [s for s in spec.slots if s.kind != "static_label"]
        if not fillable:
            raise ValueError("Nel template non sono stati riconosciuti spazi da compilare: verifica che sia un template di CV.")
        # prova di costruzione con un candidato fittizio: un errore emerge ora, non dopo la scrittura dei contenuti
        demo = PersonContent(source_file="prova", profile_id="p", profile_name="Profilo", full_name="Nome Cognome",
                             summary="Testo di prova.", skills=["Competenza"], background=["Formazione"],
                             experiences=[ExperienceBlock(title="Cliente - Progetto", role="Ruolo", bullets=["Attivita'"])],
                             extra={f.key: (["Voce"] if f.type == "list" else "Valore") for f in spec.fields})
        build_deck(spec, [demo], {}, "it", d / "prova.pptx")
        dump_spec(spec, d / "spec.json")
        names = ", ".join(sorted({s.field or s.kind for s in fillable if s.field} | {
            ln["field"] for s in fillable if s.kind == "label_lines" for ln in s.options.get("lines", [])}))
        self._log(st, "template", f"Template riconosciuto: {len(fillable)} spazi da compilare ({names})")
        return spec

    def _pipeline(self, st: RunState) -> Pipeline:
        """Pipeline nuova a ogni fase: usa sempre provider, modelli e limiti di spesa correnti."""
        llm = self._client(st)
        st.provider = settings.resolved_provider()
        st.models = {t: llm.model(t) for t in ("strong", "fast")} if st.provider != "none" else {}

        def progress(stage: str, frac: float, msg: str) -> None:
            lo, hi = STAGE_SPAN.get(stage, (st.progress, st.progress))
            self._log(st, stage, msg, progress=max(st.progress, lo + (hi - lo) * max(0.0, min(frac, 1.0))))
            self._save(st)

        return Pipeline(llm, spec=self._spec(st, llm), progress=progress)

    def _items(self, st: RunState) -> list[CVItem]:
        d = self._dir(st.id)
        by_file = {c.source_file: c for c in st.cvs}
        return [CVItem(load_document(d / "in" / f, d / "work"), by_file[f]) for f in st.cv_files if f in by_file]

    def _fail(self, st: RunState, e: Exception, back_to: Status | None = None) -> None:
        if isinstance(e, (LLMUnavailable, BudgetExceeded)):
            msg = str(e)
        else:
            msg = f"{type(e).__name__}: {e}"
            (self._dir(st.id) / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        st.error = msg
        st.status = back_to or "error"
        self._log(st, "error", msg, level="error")
        self._save(st)
        self._emit(st.id, "status", {"status": st.status, "error": msg})

    # ------------------------------------------------------------------ fase 1: creazione + analisi
    def create(self, bando: tuple[str, bytes], cvs: list[tuple[str, bytes]], template: tuple[str, bytes] | None,
               options: RunOptions) -> RunState:
        if not cvs:
            raise ValueError("Carica almeno un CV.")
        names = [n for n, _ in cvs]
        if len(set(names)) != len(names):
            raise ValueError("Ci sono CV con lo stesso nome di file: rinominali prima di caricarli.")
        run_id = uuid.uuid4().hex[:10]
        d = self._dir(run_id) / "in"
        d.mkdir(parents=True, exist_ok=True)
        for name, data in [bando, *cvs, *([template] if template else [])]:
            (d / Path(name).name).write_bytes(data)
        cfg = settings
        prov = cfg.resolved_provider()
        st = RunState(
            id=run_id, created_at=_now(), updated_at=_now(), title=Path(bando[0]).stem, options=options,
            provider=prov,
            models={} if prov == "none" else {t: cfg.model_for(prov, t) for t in ("strong", "fast")},
            bando_file=Path(bando[0]).name, cv_files=[Path(n).name for n in names],
            template_file=Path(template[0]).name if template else None,
        )
        with self._lock:
            self._runs[run_id] = st
            self._events[run_id] = []
        self._save(st)
        self._pool.submit(self._analyze, run_id)
        return st

    def reanalyze(self, run_id: str) -> RunState:
        """Rilancia l'analisi sugli stessi file (es. dopo un errore o dopo aver cambiato modello)."""
        st = self.get(run_id)
        if st.status in ("analyzing", "generating"):
            raise RuntimeError("Elaborazione gia' in corso.")
        st.status, st.error, st.progress = "queued", None, 0.0
        self._save(st)
        self._emit(run_id, "status", {"status": st.status})
        self._pool.submit(self._analyze, run_id)
        return st

    def _analyze(self, run_id: str) -> None:
        st = self.get(run_id)
        st.status, st.error, st.progress = "analyzing", None, 0.0
        self._emit(run_id, "status", {"status": st.status})
        d = self._dir(run_id)
        try:
            pipe = self._pipeline(st)
            _, bando = pipe.read_bando(d / "in" / st.bando_file)
            st.bando = bando
            if bando.title:
                st.title = bando.title
            self._log(st, "bando", f"Bando analizzato: {len(bando.profiles)} profili, lingua '{bando.language}'", progress=0.3)
            self._save(st)
            items = pipe.parse_cvs([d / "in" / f for f in st.cv_files], d / "work")
            st.cvs = [it.cv for it in items]
            st.progress = 0.75
            self._save(st)
            st.assignments = pipe.assign(items, bando)
            st.status, st.progress = "review", 1.0
            self._log(st, "match", "Analisi completata: verifica gli abbinamenti e genera la presentazione")
            self._save(st)
            self._emit(run_id, "status", {"status": st.status})
        except Exception as e:  # noqa: BLE001
            self._fail(st, e)

    # ------------------------------------------------------------------ fase 2: generazione
    def set_assignments(self, run_id: str, assignments: dict[str, Assignment],
                        names: dict[str, str | None] | None = None,
                        details: dict[str, dict] | None = None, guidance: str | None = None) -> RunState:
        """Abbinamenti CV -> profilo e interventi del bid manager prima della generazione.

        names: nomi corretti/inseriti a mano (vuoto = assente: nella presentazione resta vuoto, segnalato).
        details: per CV, dati che vanno sulla slide (location, email, phone, current_role), indicazioni per la
        scrittura (instructions) ed esclusione dalla presentazione (excluded). guidance: indicazioni per tutti."""
        st = self.get(run_id)
        if st.status not in ("review", "done", "error", "interrupted") or st.bando is None:
            raise RuntimeError("Abbinamenti modificabili solo dopo l'analisi.")
        by_file = {c.source_file: c for c in st.cvs}
        # validazione prima di toccare lo stato: una richiesta non valida non lascia modifiche a meta'
        for fn in [*(details or {}), *(names or {}), *assignments]:
            if fn not in by_file:
                raise ValueError(f"CV sconosciuto: {fn}")
        excluded = {fn: (details or {}).get(fn, {}).get("excluded", st.candidates.get(fn, CandidateEdits()).excluded)
                    for fn in by_file}
        if excluded and all(excluded.values()):
            raise ValueError("Almeno un candidato deve restare nella presentazione.")
        for fn, d in (details or {}).items():
            for key in ("location", "email", "phone", "current_role"):
                if len(str(d.get(key) or "")) > 120:
                    raise ValueError("Valore troppo lungo (max 120 caratteri).")
            if len(str(d.get("instructions") or "")) > 2000:
                raise ValueError("Indicazioni troppo lunghe (max 2000 caratteri).")
        if guidance is not None and len(guidance) > 3000:
            raise ValueError("Indicazioni troppo lunghe (max 3000 caratteri).")
        for fn, name in (names or {}).items():
            if len(" ".join((name or "").split())) > 80:
                raise ValueError("Nome troppo lungo (max 80 caratteri).")

        for fn, d in (details or {}).items():
            cv = by_file[fn]
            ed = st.candidates.get(fn) or CandidateEdits()
            for key in ("location", "email", "phone"):
                if key in d:
                    setattr(cv, key, " ".join(str(d[key] or "").split()) or None)
            if "current_role" in d:
                ed.current_role = " ".join(str(d["current_role"] or "").split()) or None
            if "instructions" in d:
                ed.instructions = str(d["instructions"] or "").strip()
            if "excluded" in d:
                ed.excluded = bool(d["excluded"])
            st.candidates[fn] = ed
        if guidance is not None:
            st.guidance = guidance.strip()
        for fn, name in (names or {}).items():
            by_file[fn].full_name = " ".join((name or "").split()) or None
        for fn, a in assignments.items():
            if fn not in st.assignments:
                raise ValueError(f"CV sconosciuto: {fn}")
            prof = st.bando.get(a.profile_id)
            if prof is None:
                raise ValueError(f"Profilo sconosciuto: {a.profile_id}")
            if a.subprofile and a.subprofile not in {s.name for s in prof.subprofiles}:
                a.subprofile = None
            old = st.assignments[fn]
            a.confidence, a.rationale = (old.confidence, old.rationale) if old.profile_id == a.profile_id else (1.0, "Scelto manualmente")
            st.assignments[fn] = a
        self._save(st)
        return st

    def included(self, st: RunState) -> list[str]:
        """CV da mettere nella presentazione (quelli non esclusi in fase di controllo)."""
        return [c.source_file for c in st.cvs if not st.candidates.get(c.source_file, CandidateEdits()).excluded]

    def estimate(self, run_id: str, visual_critic: bool | None = None) -> dict:
        st = self.get(run_id)
        if st.bando is None:
            raise RuntimeError("Stima disponibile dopo l'analisi.")
        crit = st.options.visual_critic if visual_critic is None else visual_critic
        keep = set(self.included(st))
        return estimate_generation(st.model_copy(update={"cvs": [c for c in st.cvs if c.source_file in keep]}), crit, settings)

    def set_options(self, run_id: str, visual_critic: bool | None = None, hide_companies: bool | None = None,
                    output_name: str | None = None) -> RunState:
        """Opzioni della pratica modificabili in ogni momento (il nome del file vale subito, senza rigenerare)."""
        st = self.get(run_id)
        if visual_critic is not None:
            st.options.visual_critic = visual_critic
        if hide_companies is not None:
            if st.status in ("analyzing", "generating"):
                raise RuntimeError("Elaborazione in corso: cambia l'opzione al termine.")
            st.options.hide_companies = hide_companies
        if output_name is not None:
            if output_name.strip() and not clean_output_name(output_name):
                raise ValueError("Nome del file non valido.")
            st.options.output_name = clean_output_name(output_name)
        self._save(st)
        return st

    def generate(self, run_id: str, visual_critic: bool | None = None) -> RunState:
        st = self.get(run_id)
        if st.bando is None or not st.cvs:
            raise RuntimeError("Esegui prima l'analisi.")
        if st.status in ("analyzing", "generating"):
            raise RuntimeError("Elaborazione gia' in corso.")
        if visual_critic is not None:
            st.options.visual_critic = visual_critic
        st.status, st.error, st.progress = "generating", None, 0.0
        self._save(st)
        self._emit(run_id, "status", {"status": st.status})
        self._pool.submit(self._generate, run_id)
        return st

    def _store_result(self, st: RunState, res, t0: float, edited: bool) -> None:
        d = self._dir(st.id)
        rel = lambda p: Path(p).resolve().relative_to(d.resolve()).as_posix()  # noqa: E731
        st.result = RunResultInfo(
            pptx=rel(res.pptx_path), report_md=rel(res.report_md_path), report_json=rel(res.report_json_path),
            slides=[rel(p) for p in res.slide_images], report=res.report, generated_at=_now(),
            duration_s=round(time.time() - t0, 1), edited=edited,
        )
        st.status, st.progress = "done", 1.0
        bad = [p.content.full_name or p.content.source_file for p in res.report.people if p.fit_issues]
        self._log(st, "done", "Presentazione pronta" + (f" (impaginazione da rivedere: {', '.join(bad)})" if bad else ""))
        self._save(st)
        self._emit(st.id, "status", {"status": st.status})

    def _generate(self, run_id: str) -> None:
        st = self.get(run_id)
        t0 = time.time()
        d = self._dir(run_id)
        try:
            pipe = self._pipeline(st)
            keep = set(self.included(st))
            items = [it for it in self._items(st) if it.cv.source_file in keep]
            edits = {fn: st.candidates.get(fn, CandidateEdits()) for fn in keep}
            instructions = {
                fn: "\n".join(x for x in (st.guidance, e.instructions) if x) for fn, e in edits.items()
            }
            roles = {fn: e.current_role for fn, e in edits.items() if e.current_role}
            self._log(st, "write", "In attesa del motore di rendering..." if self._render_lock.locked() else "Avvio generazione")
            with self._render_lock:
                shutil.rmtree(d / "out", ignore_errors=True)
                res = pipe.generate(st.bando, items, st.assignments, d / "out", visual_critic=st.options.visual_critic,
                                    instructions=instructions, role_overrides=roles,
                                    hide_companies=st.options.hide_companies)
            self._store_result(st, res, t0, edited=False)
        except Exception as e:  # noqa: BLE001
            self._fail(st, e, back_to="review" if isinstance(e, (LLMUnavailable, BudgetExceeded)) else None)

    # ------------------------------------------------------------------ fase 3: revisione manuale dei contenuti
    def update_person(self, run_id: str, source_file: str, content: PersonContent) -> RunState:
        st = self.get(run_id)
        if st.result is None:
            raise RuntimeError("Nessun risultato da modificare.")
        for pr in st.result.report.people:
            if pr.content.source_file == source_file:
                # campi non modificabili dalla UI restano quelli originali
                keep = pr.content.model_dump(include={"source_file", "profile_id", "coverage", "omitted"})
                new = PersonContent.model_validate({**content.model_dump(), **keep})
                if pr.content.name_is_placeholder and new.full_name.strip():
                    # nome inserito a mano dove il CV non lo riportava: l'avviso non vale piu'
                    new.name_is_placeholder = False
                    new.warnings = [w for w in new.warnings if not w.startswith("Nome non presente")]
                pr.content = new
                st.result.pending_edits = True
                self._save(st)
                return st
        raise KeyError(source_file)

    def rebuild(self, run_id: str) -> RunState:
        st = self.get(run_id)
        if st.result is None or st.bando is None:
            raise RuntimeError("Nessun risultato da ricostruire.")
        if st.status in ("analyzing", "generating"):
            raise RuntimeError("Elaborazione gia' in corso.")
        st.status, st.error, st.progress = "generating", None, 0.0
        self._save(st)
        self._emit(run_id, "status", {"status": st.status})
        self._pool.submit(self._rebuild, run_id)
        return st

    def _rebuild(self, run_id: str) -> None:
        st = self.get(run_id)
        t0 = time.time()
        d = self._dir(run_id)
        try:
            pipe = self._pipeline(st)
            items = self._items(st)
            people = st.result.report.people
            contents = [p.content.model_copy(deep=True) for p in people]
            faith = [p.faith_issues for p in people]
            with self._render_lock:
                shutil.rmtree(d / "out", ignore_errors=True)
                res = pipe.rebuild(st.bando, items, contents, faith, d / "out")
            self._store_result(st, res, t0, edited=True)
        except Exception as e:  # noqa: BLE001
            self._fail(st, e, back_to="done" if st.result else None)

    # ------------------------------------------------------------------ costi del run
    def cost(self, run_id: str) -> dict:
        led = get_ledger()
        return {"totals": led.totals(run_id=run_id), "by_stage": led.group("stage", run_id=run_id),
                "by_phase": led.group("phase", run_id=run_id)}


def to_json(obj: Any) -> Any:
    return json.loads(obj.model_dump_json()) if isinstance(obj, BaseModel) else obj
