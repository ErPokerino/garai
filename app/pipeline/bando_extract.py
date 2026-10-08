"""Estrazione dei requisiti dal bando: un profilo per chiamata (parallelo) + requisiti generali."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from app.ingestion.language import detect_language
from app.llm import prompts
from app.llm.client import LLMClient
from app.schemas import BandoSpec, ProfileSpec

from .llm_schemas import GeneralRequirements


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "profile"


def split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Divide il testo (markdown-like) alle intestazioni di livello 3: (introduzione, [(titolo, corpo)])."""
    parts = re.split(r"(?m)^### ", text)
    intro, rest = parts[0], parts[1:]
    sections = []
    for chunk in rest:
        title, _, body = chunk.partition("\n")
        sections.append((title.strip(), body.strip()))
    return intro, sections


def extract_bando(llm: LLMClient, text: str, progress=None) -> BandoSpec:
    language = detect_language(text)
    intro, sections = split_sections(text)

    if len(sections) >= 2:
        general = llm.structured(
            task="bando:general",
            system=prompts.BANDO_GENERAL_SYSTEM,
            user=intro[:20000],
            schema=GeneralRequirements,
            tier="fast",
            max_tokens=3000,
        )

        def one(item: tuple[str, str]) -> ProfileSpec:
            title, body = item
            prof = llm.structured(
                task=f"bando:profile:{_slug(title)}",
                system=prompts.BANDO_PROFILE_SYSTEM,
                user=f"SECTION HEADING: {title}\n\nSECTION TEXT:\n{body[:30000]}",
                schema=ProfileSpec,
                tier="strong",
                max_tokens=6000,
            )
            if not prof.id:
                m = re.match(r"\s*(\d+(?:\.\d+)*)", title)
                prof.id = m.group(1) if m else _slug(title)
            return prof

        with ThreadPoolExecutor(max_workers=6) as ex:
            profiles = list(ex.map(one, sections))
        return BandoSpec(
            language=language, title=general.title, general_requirements=general.requirements, profiles=profiles
        )

    # Fallback: documento senza struttura a sezioni -> una sola chiamata
    spec = llm.structured(
        task="bando:full",
        system=prompts.BANDO_FULL_SYSTEM,
        user=text[:120000],
        schema=BandoSpec,
        tier="strong",
        max_tokens=16000,
    )
    spec.language = language
    return spec
