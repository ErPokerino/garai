"""Composizione dei client LLM: provider remoto + cache su disco + fixture + metering dei costi.

    MeteredClient (ledger costi, limiti di spesa)
      └─ ChainClient (opzionale: prima le fixture, poi il provider)
           └─ CachedClient (stessi input -> nessuna nuova chiamata, registrata come risparmio)
                └─ AnthropicClient | OpenAIClient | GeminiClient | NullClient

La pipeline usa solo `llm.structured(...)`: il resto e' trasparente.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.config import PROVIDERS, Settings, settings

from .base import BudgetExceeded, LLMClient, LLMUnavailable, Usage, UsageClient
from .pricing import PriceBook
from .providers import AnthropicClient, GeminiClient, OpenAIClient
from .usage import MeteredClient, UsageLedger

__all__ = [
    "LLMClient", "LLMUnavailable", "BudgetExceeded", "FixtureClient", "CachedClient", "ChainClient", "NullClient",
    "AnthropicClient", "OpenAIClient", "GeminiClient", "MeteredClient", "build_client", "has_remote", "get_ledger",
    "get_prices",
]


def _slug(task: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task)


class FixtureClient(UsageClient):
    """Risposte prefabbricate: legge `<dir>/<task>.json`. Se manca solleva LLMUnavailable."""

    id = "fixtures"

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)

    def model(self, tier: str) -> str:
        return "fixture"

    def structured_with_usage(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        p = self.dir / f"{_slug(task)}.json"
        if not p.exists():
            raise LLMUnavailable(f"nessuna fixture per il task '{task}' ({p.name})")
        return schema.model_validate_json(p.read_text(encoding="utf-8")), Usage(provider="fixtures", model="fixture")


class CachedClient(UsageClient):
    """Cache su disco sopra un client reale. La chiave include provider, modello, task, prompt e schema.

    Il file conserva anche il consumo originale: un riuso viene registrato a costo zero con il risparmio ottenuto.
    """

    def __init__(self, inner: UsageClient, cache_dir: Path | None = None):
        self.inner = inner
        self.dir = Path(cache_dir or settings.cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.id = getattr(inner, "id", "llm")
        self._lock = threading.Lock()

    def model(self, tier: str) -> str:
        return self.inner.model(tier)

    def _key(self, task, system, user, schema, tier, images) -> str:
        h = hashlib.sha256()
        for part in (self.id, self.inner.model(tier), task, system, user, schema.__name__,
                     json.dumps(schema.model_json_schema(), sort_keys=True)):
            h.update(part.encode("utf-8"))
            h.update(b"\0")
        for p in images or []:
            h.update(Path(p).read_bytes())
        return h.hexdigest()[:32]

    def structured_with_usage(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        key = self._key(task, system, user, schema, tier, images)
        f = self.dir / f"{_slug(task)[:40]}_{key}.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "output" in data and "usage" in data:
                u = Usage.from_dict(data["usage"])
                out = schema.model_validate(data["output"])
            else:  # formato precedente (solo output)
                u = Usage(provider=self.id, model=self.inner.model(tier))
                out = schema.model_validate(data)
            u.local_cache_hit, u.latency_ms, u.attempts = True, 0, 0
            return out, u
        out, u = self.inner.structured_with_usage(
            task=task, system=system, user=user, schema=schema, tier=tier, images=images, max_tokens=max_tokens
        )
        with self._lock:
            f.write_text(json.dumps({"output": out.model_dump(mode="json"), "usage": u.to_dict()}, ensure_ascii=False,
                                    indent=1), encoding="utf-8")
        return out, u


class ChainClient(UsageClient):
    """Prova i client in ordine (es. fixture, poi provider remoto)."""

    def __init__(self, *clients: UsageClient):
        self.clients = clients
        self.id = "+".join(getattr(c, "id", "llm") for c in clients)

    def model(self, tier: str) -> str:
        return self.clients[-1].model(tier)

    def structured_with_usage(self, **kw):
        last: Exception | None = None
        for c in self.clients:
            try:
                return c.structured_with_usage(**kw)
            except LLMUnavailable as e:
                last = e
        raise last or LLMUnavailable("nessun client disponibile")


class NullClient(UsageClient):
    id = "none"

    def model(self, tier: str) -> str:
        return "none"

    def structured_with_usage(self, **kw):
        raise LLMUnavailable(
            "Nessun provider LLM configurato: inserisci una API key (Anthropic, OpenAI o Gemini) nelle Impostazioni."
        )


@lru_cache(maxsize=4)
def _prices_for(path: str) -> PriceBook:
    return PriceBook(Path(path))


def get_prices(cfg: Settings = settings) -> PriceBook:
    return _prices_for(str(cfg.data_dir / "pricing.json"))


@lru_cache(maxsize=4)
def _ledger_for(path: str, prices_path: str) -> UsageLedger:
    return UsageLedger(Path(path), _prices_for(prices_path))


def get_ledger(cfg: Settings = settings) -> UsageLedger:
    return _ledger_for(str(cfg.data_dir / "garai.db"), str(cfg.data_dir / "pricing.json"))


def _remote(cfg: Settings) -> UsageClient:
    provider = cfg.resolved_provider()
    if provider in PROVIDERS and not cfg.api_key(provider):
        return NullClient()
    if provider == "anthropic":
        return AnthropicClient(cfg)
    if provider == "openai":
        return OpenAIClient(cfg)
    if provider == "gemini":
        return GeminiClient(cfg)
    return NullClient()


def build_client(
    cfg: Settings = settings,
    fixtures_dir: str | Path | None = None,
    use_cache: bool = True,
    run_id: str | None = None,
    on_call: Callable[[dict], None] | None = None,
    metered: bool = True,
    remote: bool = True,
) -> MeteredClient | UsageClient:
    """remote=False: nessuna chiamata a provider a pagamento (es. test: solo fixture; cio' che manca degrada
    in modo deterministico come senza chiave)."""
    real = _remote(cfg) if remote else NullClient()
    if use_cache and not isinstance(real, NullClient):
        real = CachedClient(real, cfg.cache_dir)
    client: UsageClient = ChainClient(FixtureClient(fixtures_dir), real) if fixtures_dir else real
    if not metered:
        return client
    return MeteredClient(client, get_ledger(cfg), run_id=run_id, run_budget_usd=cfg.run_budget_usd,
                         monthly_budget_usd=cfg.monthly_budget_usd, on_call=on_call)


def has_remote(cfg: Settings = settings) -> bool:
    p = cfg.resolved_provider()
    return p in PROVIDERS and bool(cfg.api_key(p))
