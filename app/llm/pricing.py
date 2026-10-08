"""Listino prezzi dei modelli (USD per 1M token) e calcolo del costo di una chiamata.

I prezzi cambiano nel tempo: ogni modello ha una lista di fasce con data di inizio validita'. I valori si possono
sovrascrivere senza toccare il codice con `data/pricing.json` (stesso formato di `BUILTIN`, modificabile dalla UI).
Fonti: ai.google.dev/gemini-api/docs/pricing (Gemini, ott. 2026), platform.claude.com (Claude, ott. 2026).
I prezzi OpenAI sono indicativi e marcati come da verificare.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# model -> lista di fasce {from, input, output, cache_read, cache_write}; "verified": prezzo controllato sulla fonte ufficiale
BUILTIN: dict[str, dict] = {
    # ---------------------------------------------------------------- Google Gemini
    "gemini-3.8-flash": {
        "provider": "gemini", "label": "Gemini 3.8 Flash", "verified": True,
        "tiers": [
            {"from": "2000-01-01", "input": 0.75, "output": 3.75, "cache_read": 0.075},
            {"from": "2027-01-01", "input": 1.50, "output": 7.50, "cache_read": 0.15},
        ],
    },
    "gemini-3.7-flash": {
        "provider": "gemini", "label": "Gemini 3.7 Flash", "verified": True,
        "tiers": [
            {"from": "2000-01-01", "input": 0.75, "output": 3.75, "cache_read": 0.075},
            {"from": "2027-01-01", "input": 1.50, "output": 7.50, "cache_read": 0.15},
        ],
    },
    "gemini-3.5-flash": {
        "provider": "gemini", "label": "Gemini 3.5 Flash", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 1.50, "output": 9.00, "cache_read": 0.15}],
    },
    "gemini-3.5-flash-lite": {
        "provider": "gemini", "label": "Gemini 3.5 Flash-Lite", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 0.30, "output": 2.50, "cache_read": 0.03}],
    },
    "gemini-3.1-flash-lite": {
        "provider": "gemini", "label": "Gemini 3.1 Flash-Lite", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 0.25, "output": 1.50, "cache_read": 0.025}],
    },
    "gemini-3.1-pro-preview": {
        "provider": "gemini", "label": "Gemini 3.1 Pro (preview, prompt <=200k)", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 2.00, "output": 12.00, "cache_read": 0.20}],
    },
    "gemini-2.5-flash": {
        "provider": "gemini", "label": "Gemini 2.5 Flash", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 0.30, "output": 2.50, "cache_read": 0.03}],
    },
    # ---------------------------------------------------------------- Anthropic Claude (cache_write = TTL 5 minuti)
    "claude-opus-5-5": {
        "provider": "anthropic", "label": "Claude Opus 5.5", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00}],
    },
    "claude-sonnet-5-5": {
        "provider": "anthropic", "label": "Claude Sonnet 5.5", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50}],
    },
    "claude-haiku-5-5": {
        "provider": "anthropic", "label": "Claude Haiku 5.5", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}],
    },
    "claude-sonnet-4-5": {
        "provider": "anthropic", "label": "Claude Sonnet 4.5", "verified": False,
        "tiers": [{"from": "2000-01-01", "input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75}],
    },
    "claude-haiku-4-5": {
        "provider": "anthropic", "label": "Claude Haiku 4.5", "verified": True,
        "tiers": [{"from": "2000-01-01", "input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25}],
    },
    # ---------------------------------------------------------------- OpenAI (indicativi)
    "gpt-5": {
        "provider": "openai", "label": "GPT-5", "verified": False,
        "tiers": [{"from": "2000-01-01", "input": 1.25, "output": 10.00, "cache_read": 0.125}],
    },
    "gpt-5-mini": {
        "provider": "openai", "label": "GPT-5 mini", "verified": False,
        "tiers": [{"from": "2000-01-01", "input": 0.25, "output": 2.00, "cache_read": 0.025}],
    },
}


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


class PriceBook:
    def __init__(self, override_file: Path | None = None):
        self.override_file = override_file
        self._lock = threading.Lock()

    def _overrides(self) -> dict:
        if self.override_file and self.override_file.exists():
            try:
                return json.loads(self.override_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
        return {}

    def catalog(self) -> dict[str, dict]:
        out = {k: dict(v) for k, v in BUILTIN.items()}
        for model, entry in self._overrides().items():
            base = out.get(model, {"provider": entry.get("provider", "custom"), "label": model})
            out[model] = {**base, **entry, "overridden": True}
        return out

    def set_override(self, model: str, entry: dict | None) -> None:
        """Imposta (o rimuove con None) un prezzo personalizzato per un modello."""
        if not self.override_file:
            raise RuntimeError("PriceBook senza file di override")
        with self._lock:
            data = self._overrides()
            if entry is None:
                data.pop(model, None)
            else:
                data[model] = entry
            self.override_file.parent.mkdir(parents=True, exist_ok=True)
            self.override_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def price(self, model: str, on: date | None = None) -> Price | None:
        entry = self.catalog().get(model)
        if entry is None:
            # modelli con suffissi (es. "-preview-09-2026", "-001"): prova il prefisso piu' lungo noto
            cands = [m for m in self.catalog() if model.startswith(m)]
            if not cands:
                return None
            entry = self.catalog()[max(cands, key=len)]
        on = on or date.today()
        tiers = sorted(entry.get("tiers", []), key=lambda t: t.get("from", "2000-01-01"))
        active = None
        for t in tiers:
            if date.fromisoformat(t.get("from", "2000-01-01")) <= on:
                active = t
        if active is None:
            return None
        inp = float(active.get("input", 0))
        return Price(
            input=inp,
            output=float(active.get("output", 0)),
            cache_read=float(active.get("cache_read", inp * 0.1)),
            cache_write=float(active.get("cache_write", inp)),
        )

    def cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        on: date | None = None,
    ) -> tuple[float, bool]:
        """Costo in USD. `input_tokens` = token di input NON in cache; `output_tokens` include il ragionamento.
        Ritorna (costo, prezzo_noto)."""
        p = self.price(model, on)
        if p is None:
            return 0.0, False
        usd = (
            input_tokens * p.input
            + output_tokens * p.output
            + cache_read_tokens * p.cache_read
            + cache_write_tokens * p.cache_write
        ) / 1_000_000
        return usd, True
