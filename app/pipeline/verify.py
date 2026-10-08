"""Verifica di fedelta': ogni affermazione della slide deve essere sostenuta dal CV sorgente."""
from __future__ import annotations

import json

from app.llm import prompts
from app.llm.client import LLMClient
from app.schemas import FaithIssue, PersonContent

from .llm_schemas import VerifyResult


def _slide_payload(c: PersonContent) -> dict:
    return {
        "name": c.full_name,
        "current_role": c.current_role,
        "current_company": c.current_company,
        "summary": c.summary,
        "background": c.background,
        "skills": c.skills,
        "experiences": [e.model_dump(exclude={"source_indices"}) for e in c.experiences],
    }


def verify_content(llm: LLMClient, cv_text: str, content: PersonContent) -> list[FaithIssue]:
    user = f"SOURCE CV TEXT:\n{cv_text[:70000]}\n\nSLIDE CONTENT (JSON):\n" + json.dumps(_slide_payload(content), ensure_ascii=False)
    res = llm.structured(
        task=f"verify:{content.source_file.rsplit('.', 1)[0]}",
        system=prompts.VERIFY_SYSTEM,
        user=user,
        schema=VerifyResult,
        tier="fast",
        max_tokens=3000,
    )
    return res.issues
