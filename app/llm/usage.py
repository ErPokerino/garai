"""Monitoraggio dei costi: registro (SQLite) di ogni chiamata LLM, aggregazioni e limiti di spesa."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .base import BudgetExceeded, Usage, UsageClient, stage_of
from .pricing import PriceBook

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id TEXT,
    phase TEXT,
    stage TEXT NOT NULL,
    task TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tier TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    thinking_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    saved_usd REAL DEFAULT 0,
    price_known INTEGER DEFAULT 1,
    local_cache_hit INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 1,
    status TEXT DEFAULT 'ok',
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_calls_ts ON llm_calls(ts);
CREATE INDEX IF NOT EXISTS ix_calls_run ON llm_calls(run_id);
"""

STAGE_LABELS = {
    "bando": "Estrazione bando",
    "cv_parse": "Parsing CV",
    "match": "Abbinamento",
    "write": "Scrittura contenuti",
    "verify": "Verifica fedeltà",
    "critic": "Critico visivo",
    "translate_labels": "Traduzione etichette",
    "template": "Analisi template",
    "ping": "Test connessione",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UsageLedger:
    def __init__(self, db_path: Path, prices: PriceBook):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.prices = prices
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    # ------------------------------------------------------------------ scrittura
    def record(
        self, *, task: str, tier: str, usage: Usage, run_id: str | None, phase: str | None,
        status: str = "ok", error: str | None = None,
    ) -> dict:
        cost, known = self.prices.cost(
            usage.model, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, usage.cache_write_tokens
        )
        saved = 0.0
        if usage.local_cache_hit:  # la chiamata non e' stata fatta: il costo originale diventa risparmio
            saved, cost = cost, 0.0
        row = dict(
            ts=_utcnow(), run_id=run_id, phase=phase, stage=stage_of(task), task=task, provider=usage.provider,
            model=usage.model, tier=tier, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            thinking_tokens=usage.thinking_tokens, cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens, cost_usd=round(cost, 8), saved_usd=round(saved, 8),
            price_known=int(known), local_cache_hit=int(usage.local_cache_hit), latency_ms=usage.latency_ms,
            attempts=usage.attempts, status=status, error=(error or "")[:500] or None,
        )
        cols = ",".join(row)
        with self._lock, self._conn() as c:
            cur = c.execute(f"INSERT INTO llm_calls ({cols}) VALUES ({','.join('?' * len(row))})", list(row.values()))
            row["id"] = cur.lastrowid
        return row

    # ------------------------------------------------------------------ lettura
    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    @staticmethod
    def _where(start: str | None, end: str | None, run_id: str | None = None) -> tuple[str, tuple]:
        cond, args = [], []
        if start:
            cond.append("ts >= ?")
            args.append(start)
        if end:
            cond.append("ts < ?")
            args.append(end)
        if run_id:
            cond.append("run_id = ?")
            args.append(run_id)
        return ("WHERE " + " AND ".join(cond)) if cond else "", tuple(args)

    _AGG = """COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost_usd, COALESCE(SUM(saved_usd),0) AS saved_usd,
        COALESCE(SUM(input_tokens),0) AS input_tokens, COALESCE(SUM(output_tokens),0) AS output_tokens,
        COALESCE(SUM(thinking_tokens),0) AS thinking_tokens, COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
        COALESCE(SUM(local_cache_hit),0) AS cache_hits, COALESCE(SUM(status='error'),0) AS errors,
        COALESCE(SUM(price_known=0),0) AS unpriced, COALESCE(AVG(latency_ms),0) AS avg_latency_ms"""

    def totals(self, start=None, end=None, run_id=None) -> dict:
        w, a = self._where(start, end, run_id)
        return self._q(f"SELECT {self._AGG} FROM llm_calls {w}", a)[0]

    def group(self, by: str, start=None, end=None, run_id=None) -> list[dict]:
        expr = {"day": "substr(ts,1,10)", "model": "model", "provider": "provider", "stage": "stage",
                "run": "run_id", "phase": "phase"}[by]
        w, a = self._where(start, end, run_id)
        return self._q(f"SELECT {expr} AS key, {self._AGG} FROM llm_calls {w} GROUP BY key ORDER BY key", a)

    def daily(self, start=None, end=None, tz=None) -> tuple[list[dict], list[dict]]:
        """Spesa per giorno e per giorno/modello nel fuso `tz` (i timestamp sono UTC: si aggrega al minuto e si converte)."""
        tz = tz or timezone.utc
        w, a = self._where(start, end)
        rows = self._q(
            f"SELECT substr(ts,1,16) AS minute, model, COALESCE(SUM(cost_usd),0) AS cost_usd, COUNT(*) AS calls "
            f"FROM llm_calls {w} GROUP BY minute, model", a)
        days: dict[str, dict] = {}
        day_model: dict[tuple[str, str], dict] = {}
        for r in rows:
            day = datetime.fromisoformat(r["minute"]).replace(tzinfo=timezone.utc).astimezone(tz).date().isoformat()
            d = days.setdefault(day, {"key": day, "cost_usd": 0.0, "calls": 0})
            dm = day_model.setdefault((day, r["model"]), {"day": day, "model": r["model"], "cost_usd": 0.0, "calls": 0})
            for x in (d, dm):
                x["cost_usd"] += r["cost_usd"]
                x["calls"] += r["calls"]
        return [days[k] for k in sorted(days)], [day_model[k] for k in sorted(day_model)]

    def calls(self, start=None, end=None, run_id=None, limit: int = 200) -> list[dict]:
        w, a = self._where(start, end, run_id)
        return self._q(f"SELECT * FROM llm_calls {w} ORDER BY id DESC LIMIT ?", a + (limit,))

    def run_cost(self, run_id: str) -> float:
        return float(self.totals(run_id=run_id)["cost_usd"])

    def month_cost(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return float(self.totals(start=f"{now:%Y-%m}-01")["cost_usd"])


class MeteredClient(UsageClient):
    """Registra ogni chiamata nel ledger e applica i limiti di spesa prima di chiamare il provider."""

    def __init__(
        self,
        inner: UsageClient,
        ledger: UsageLedger,
        run_id: str | None = None,
        run_budget_usd: float = 0.0,
        monthly_budget_usd: float = 0.0,
        on_call: Callable[[dict], None] | None = None,
    ):
        self.inner = inner
        self.ledger = ledger
        self.run_id = run_id
        self.phase: str | None = None  # "analysis" | "generation" | "rebuild" (impostata dalla pipeline)
        self.run_budget_usd = run_budget_usd
        self.monthly_budget_usd = monthly_budget_usd
        self.on_call = on_call
        self.id = getattr(inner, "id", "llm")

    def model(self, tier: str) -> str:
        return self.inner.model(tier)

    def _check_budget(self) -> None:
        if self.run_budget_usd > 0 and self.run_id:
            spent = self.ledger.run_cost(self.run_id)
            if spent >= self.run_budget_usd:
                raise BudgetExceeded(
                    f"Limite di spesa per run raggiunto: ${spent:.4f} su ${self.run_budget_usd:.2f}. "
                    "Aumenta il limite nelle Impostazioni per proseguire."
                )
        if self.monthly_budget_usd > 0:
            spent = self.ledger.month_cost()
            if spent >= self.monthly_budget_usd:
                raise BudgetExceeded(f"Budget mensile raggiunto: ${spent:.2f} su ${self.monthly_budget_usd:.2f}.")

    def structured_with_usage(self, **kw):
        task, tier = kw["task"], kw.get("tier", "strong")
        self._check_budget()
        try:
            out, usage = self.inner.structured_with_usage(**kw)
        except Exception as e:
            from .base import LLMUnavailable

            if not isinstance(e, (LLMUnavailable, BudgetExceeded)):
                self.ledger.record(
                    task=task, tier=tier, run_id=self.run_id, phase=self.phase, status="error", error=str(e),
                    usage=Usage(provider=self.id, model=self.inner.model(tier)),
                )
            raise
        if usage.provider == "fixtures":  # risposte prefabbricate (demo/test): nessun costo da registrare
            return out, usage
        row = self.ledger.record(task=task, tier=tier, usage=usage, run_id=self.run_id, phase=self.phase)
        if self.on_call:
            try:
                self.on_call(row)
            except Exception:  # noqa: BLE001 - la notifica non deve mai bloccare la pipeline
                pass
        return out, usage
