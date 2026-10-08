"""Tipi comuni del layer LLM: protocollo dei client, consumo di token, eccezioni."""
from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """Nessun provider configurato (manca la API key) e nessuna fixture per il task richiesto."""


class BudgetExceeded(RuntimeError):
    """Il limite di spesa impostato (per run o mensile) e' stato raggiunto: nessuna nuova chiamata."""


@dataclass
class Usage:
    """Consumo di una chiamata. `input_tokens` esclude i token letti/scritti in cache; `output_tokens` include il ragionamento."""

    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0  # gia' inclusi in output_tokens, esposti a parte per trasparenza
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1
    local_cache_hit: bool = False  # risposta servita dalla cache su disco: costo 0

    def add(self, other: "Usage") -> None:
        """Somma i consumi di un tentativo successivo (es. ritentativo dopo output non valido)."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.thinking_tokens += other.thinking_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Usage":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class LLMClient(Protocol):
    id: str

    def structured(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        tier: str = "strong",
        images: list[Path] | None = None,
        max_tokens: int = 8000,
    ) -> T: ...


class UsageClient:
    """Base per i client che restituiscono anche il consumo: `structured()` scarta l'usage."""

    id = "llm"

    def structured_with_usage(self, **kw) -> tuple[BaseModel, Usage]:  # pragma: no cover - astratto
        raise NotImplementedError

    def structured(self, **kw):
        return self.structured_with_usage(**kw)[0]

    def model(self, tier: str) -> str:
        return tier


def img_b64(p: Path) -> tuple[str, str]:
    data = Path(p).read_bytes()
    mt = "image/png" if str(p).lower().endswith("png") else "image/jpeg"
    return mt, base64.b64encode(data).decode()


def json_from_text(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def stage_of(task: str) -> str:
    """'cv_parse:CV_DEV' -> 'cv_parse'."""
    return task.split(":", 1)[0]
