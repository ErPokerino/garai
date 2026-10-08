"""Caricamento del Template Spec e delle etichette nella lingua di output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.config import ROOT
from app.schemas import TemplateSpec

DEFAULT_SPEC = ROOT / "templates" / "abstract_cv.spec.json"


def load_spec(path: str | Path = DEFAULT_SPEC) -> TemplateSpec:
    return TemplateSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def template_path(spec: TemplateSpec) -> Path:
    p = Path(spec.template_file)
    return p if p.is_absolute() else ROOT / p


def resolve_labels(
    spec: TemplateSpec,
    language: str,
    translator: Callable[[dict[str, str], str], dict[str, str]] | None = None,
) -> dict[str, str]:
    """label_key -> testo nella lingua richiesta.

    Se la lingua non e' presente nello spec, si traduce dall'inglese tramite `translator`
    (tipicamente una chiamata LLM); senza traduttore si ricade sull'inglese.
    """
    out: dict[str, str] = {}
    missing: dict[str, str] = {}
    for key, per_lang in spec.labels.items():
        if language in per_lang:
            out[key] = per_lang[language]
        else:
            base = per_lang.get("en") or next(iter(per_lang.values()))
            out[key] = base
            missing[key] = base
    if missing and translator is not None:
        try:
            out.update(translator(missing, language))
        except Exception:  # la traduzione delle etichette non deve bloccare la generazione
            pass
    return out


def dump_spec(spec: TemplateSpec, path: str | Path) -> None:
    Path(path).write_text(json.dumps(spec.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
