"""Critico visivo (LLM con visione): confronta le slide renderizzate con il template di riferimento. Solo reportistica."""
from __future__ import annotations

from pathlib import Path

from app.llm import prompts
from app.llm.client import LLMClient

from .llm_schemas import CriticResult, Translation


def visual_review(llm: LLMClient, template_images: list[Path], rendered_images: list[Path], label: str) -> list[str]:
    res = llm.structured(
        task=f"critic:{label}",
        system=prompts.CRITIC_SYSTEM,
        user=(
            f"The first {len(template_images)} image(s) are the TEMPLATE reference slides; "
            f"the next {len(rendered_images)} image(s) are the RENDERED slides for '{label}'. Review the rendered ones."
        ),
        schema=CriticResult,
        tier="strong",
        images=[*template_images, *rendered_images],
        max_tokens=1500,
    )
    return res.notes


def translate_labels(llm: LLMClient, labels: dict[str, str], language: str) -> dict[str, str]:
    res = llm.structured(
        task=f"translate_labels:{language}",
        system=prompts.TRANSLATE_SYSTEM,
        user=f"Target language: {prompts.language_name(language)}\nLabels (JSON): {labels}",
        schema=Translation,
        tier="fast",
        max_tokens=1000,
    )
    return {it.key: it.text for it in res.items if it.key in labels}
