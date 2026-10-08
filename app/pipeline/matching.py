"""Assegnazione di ciascun CV al profilo del bando piu' adatto."""
from __future__ import annotations

import json

from app.llm import prompts
from app.llm.client import LLMClient
from app.schemas import BandoSpec, CVCanonical

from .llm_schemas import Assignment


def _cv_brief(cv: CVCanonical) -> dict:
    return {
        "file_name": cv.source_file,
        "headline": cv.headline,
        "experiences": [
            {
                "role": e.role,
                "company": e.company,
                "period": f"{e.start or '?'} - {'present' if e.is_current else (e.end or '?')}",
                "technologies": e.technologies[:8],
            }
            for e in cv.experiences[:12]
        ],
        "skills": cv.skills[:25],
        "certifications": cv.certifications[:10],
    }


def _catalog(bando: BandoSpec) -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "purpose": p.purpose[:240],
            "key_requirements": p.min_requirements[:3],
            "key_skills": p.skills_required[:4],
            "subprofiles": [s.name for s in p.subprofiles],
        }
        for p in bando.profiles
    ]


def assign_profile(llm: LLMClient, cv: CVCanonical, bando: BandoSpec) -> Assignment:
    user = (
        "PROFILE CATALOGUE:\n"
        + json.dumps(_catalog(bando), ensure_ascii=False)
        + "\n\nCANDIDATE CV SUMMARY:\n"
        + json.dumps(_cv_brief(cv), ensure_ascii=False)
    )
    a = llm.structured(
        task=f"match:{cv.source_file.rsplit('.', 1)[0]}",
        system=prompts.MATCH_SYSTEM,
        user=user,
        schema=Assignment,
        tier="fast",
        max_tokens=800,
    )
    prof = bando.get(a.profile_id)
    if prof is None:  # id inesistente: ripiega sul primo profilo e segnala bassa confidenza
        return Assignment(profile_id=bando.profiles[0].id, confidence=0.0, rationale="profilo non riconosciuto dal modello")
    names = {s.name for s in prof.subprofiles}
    if a.subprofile and a.subprofile not in names:
        a.subprofile = None
    return a
