"""Parsing e normalizzazione dei CV in CVCanonical."""
from __future__ import annotations

import re

from app.ingestion.loader import SourceDocument
from app.llm import prompts
from app.llm.client import LLMClient
from app.schemas import CVCanonical

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{7,17}\d)(?!\d)")
NAME_JUNK = re.compile(r"^(codice|code|cv|curriculum)\b|^cv[a-z]{1,4}\d+$", re.I)


def _first_phone(text: str) -> str | None:
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if 9 <= len(digits) <= 14 and not re.match(r"^(19|20)\d{2}", digits):
            return " ".join(m.group(1).split())
    return None


def parse_cv(llm: LLMClient, doc: SourceDocument) -> CVCanonical:
    images = doc.page_images if doc.scanned else None
    cv = llm.structured(
        task=f"cv_parse:{doc.path.stem}",
        system=prompts.CV_PARSE_SYSTEM,
        user=f"FILE NAME: {doc.filename}\n\nCV TEXT:\n{doc.text[:70000]}",
        schema=CVCanonical,
        tier="strong",
        images=images,
        max_tokens=12000,
    )
    cv.source_file = doc.filename
    # ripulitura deterministica
    if cv.full_name and (NAME_JUNK.search(cv.full_name.strip()) or len(cv.full_name.split()) > 5):
        cv.full_name = None
    if not cv.email:
        m = EMAIL_RE.search(doc.text)
        cv.email = m.group(0) if m else None
    if not cv.phone:
        cv.phone = _first_phone(doc.text)
    return cv
