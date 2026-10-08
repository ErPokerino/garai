"""Proposta di Template Spec da parte di un LLM con visione (per template nuovi). Da validare a mano una volta sola."""
from __future__ import annotations

import json
from pathlib import Path

from app.llm import prompts
from app.llm.client import LLMClient
from app.schemas import TemplateSpec

from .inventory import inventory
from .spec import DEFAULT_SPEC, load_spec


def propose_spec(llm: LLMClient, pptx_path: str | Path, rendered_images: list[Path]) -> TemplateSpec:
    reference = load_spec(DEFAULT_SPEC).model_dump_json()  # esempio di spec valido come formato di riferimento
    user = (
        "SHAPE INVENTORY (JSON):\n"
        + json.dumps(inventory(pptx_path), ensure_ascii=False)
        + "\n\nEXAMPLE OF A VALID SPEC FOR ANOTHER TEMPLATE (format reference only):\n"
        + reference
        + f"\n\nReturn the spec for this template; set template_file to '{pptx_path}'."
    )
    return llm.structured(
        task="template:propose_spec",
        system=prompts.TEMPLATE_ANALYST_SYSTEM,
        user=user,
        schema=TemplateSpec,
        tier="strong",
        images=rendered_images,
        max_tokens=12000,
    )
