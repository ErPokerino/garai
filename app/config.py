"""Configurazione centrale.

Priorita' (dalla piu' alta): impostazioni salvate dalla UI in `data/settings.json` > variabili d'ambiente / .env > default.
Le API key salvate dalla UI restano solo sul disco locale (cartella `data/`, esclusa dal versionamento) e non vengono
mai restituite in chiaro dalle API.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROVIDERS = ("anthropic", "openai", "gemini")
REASONING_LEVELS = ("auto", "minimal", "low", "medium", "high")

# Modelli di default per provider e livello. "strong": estrazione bando, parsing CV, writer, critico visivo.
# "fast": abbinamento, verifica di fedelta', requisiti generali, traduzione etichette.
DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {"strong": "claude-sonnet-5-5", "fast": "claude-haiku-5-5"},
    "openai": {"strong": "gpt-5", "fast": "gpt-5-mini"},
    "gemini": {"strong": "gemini-3.8-flash", "fast": "gemini-3.5-flash-lite"},
}

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_models() -> dict[str, dict[str, str]]:
    out = {p: dict(m) for p, m in DEFAULT_MODELS.items()}
    for p in PROVIDERS:
        for tier in ("strong", "fast"):
            v = os.environ.get(f"{p.upper()}_MODEL_{tier.upper()}")
            if v:
                out[p][tier] = v
    return out


def _env_keys() -> dict[str, str]:
    keys = {p: os.environ.get(env, "") for p, env in KEY_ENV.items()}
    if not keys["gemini"]:
        keys["gemini"] = os.environ.get("GOOGLE_API_KEY", "")
    return keys


@dataclass
class Settings:
    # "auto" (usa il primo provider con chiave) | "anthropic" | "openai" | "gemini" | "none"
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))
    api_keys: dict[str, str] = field(default_factory=_env_keys)
    models: dict[str, dict[str, str]] = field(default_factory=_env_models)
    # Profondita' di ragionamento per livello: auto = default del modello (mappata su effort / thinking_level).
    reasoning: dict[str, str] = field(default_factory=lambda: {"strong": "auto", "fast": "auto"})
    # Limiti di spesa in USD (0 = nessun limite). Il limite per run interrompe la generazione al superamento.
    run_budget_usd: float = field(default_factory=lambda: float(_env("RUN_BUDGET_USD", "0")))
    monthly_budget_usd: float = field(default_factory=lambda: float(_env("MONTHLY_BUDGET_USD", "0")))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(ROOT / "data"))))
    cache_dir: Path = field(default_factory=lambda: Path(_env("LLM_CACHE_DIR", str(ROOT / ".cache" / "llm"))))
    out_dir: Path = field(default_factory=lambda: Path(_env("OUT_DIR", str(ROOT / "out"))))
    # riscritture LLM ammesse quando il testo non entra nel template (poi solo riduzione deterministica)
    max_fit_iterations: int = field(default_factory=lambda: int(_env("MAX_FIT_ITERATIONS", "2")))
    max_experiences: int = field(default_factory=lambda: int(_env("MAX_EXPERIENCES", "6")))

    # ------------------------------------------------------------------ compatibilita' con il codice esistente
    @property
    def anthropic_strong(self) -> str:
        return self.models["anthropic"]["strong"]

    @property
    def anthropic_fast(self) -> str:
        return self.models["anthropic"]["fast"]

    @property
    def openai_strong(self) -> str:
        return self.models["openai"]["strong"]

    @property
    def openai_fast(self) -> str:
        return self.models["openai"]["fast"]

    # ------------------------------------------------------------------
    def api_key(self, provider: str) -> str:
        return (self.api_keys.get(provider) or "").strip()

    def resolved_provider(self) -> str:
        if self.provider != "auto":
            return self.provider
        for p in PROVIDERS:
            if self.api_key(p):
                return p
        return "none"

    def model_for(self, provider: str, tier: str) -> str:
        return self.models.get(provider, {}).get(tier) or DEFAULT_MODELS[provider][tier]


# Campi persistiti dalla UI (gli altri restano governati da env)
_PERSISTED = ("provider", "api_keys", "models", "reasoning", "run_budget_usd", "monthly_budget_usd",
              "max_fit_iterations", "max_experiences")
_lock = threading.Lock()


def settings_file(cfg: Settings | None = None) -> Path:
    return (cfg or settings).data_dir / "settings.json"


def _apply(cfg: Settings, data: dict) -> None:
    for k in _PERSISTED:
        if k not in data or data[k] is None:
            continue
        v = data[k]
        if k == "api_keys":
            for p, key in v.items():
                if p in PROVIDERS and key is not None:
                    cfg.api_keys[p] = key
        elif k == "models":
            for p, tiers in v.items():
                if p in PROVIDERS:
                    for t, m in tiers.items():
                        if t in ("strong", "fast") and m:
                            cfg.models[p][t] = m
        elif k == "reasoning":
            for t, lvl in v.items():
                if t in ("strong", "fast") and lvl in REASONING_LEVELS:
                    cfg.reasoning[t] = lvl
        else:
            typ = type(getattr(cfg, k))
            setattr(cfg, k, typ(v))


def load_persisted(cfg: Settings) -> None:
    f = settings_file(cfg)
    if f.exists():
        try:
            _apply(cfg, json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass


def save_settings(patch: dict, cfg: Settings | None = None) -> Settings:
    """Aggiorna le impostazioni in memoria e le salva su disco. Le chiavi vuote ("") cancellano la chiave salvata."""
    cfg = cfg or settings
    with _lock:
        _apply(cfg, patch)
        f = settings_file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        data = {k: getattr(cfg, k) for k in _PERSISTED}
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def mask_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    return f"{key[:4]}…{key[-4:]}" if len(key) > 12 else "••••"


settings = Settings()
load_persisted(settings)

__all__ = ["ROOT", "PROVIDERS", "REASONING_LEVELS", "DEFAULT_MODELS", "Settings", "settings", "save_settings", "mask_key"]
