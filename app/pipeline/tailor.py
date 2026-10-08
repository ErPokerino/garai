"""Writer/Tailor: selezione, riordino e sintesi del CV in funzione del profilo del bando, dentro i budget del template."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from app.llm import prompts
from app.llm.client import LLMClient
from app.schemas import BandoSpec, CVCanonical, ExperienceBlock, PersonContent, ProfileSpec, WriterOutput
from app.template.budget import Budgets

from .experience import end_sort_key, format_experience, total_months
from .names import invent_name


def _profile_payload(profile: ProfileSpec, bando: BandoSpec, subprofile: str | None) -> dict:
    return {
        "profile": profile.model_dump(exclude_none=True),
        "target_subprofile": subprofile,
        "tender_general_requirements": bando.general_requirements,
    }


def write_content(
    llm: LLMClient,
    cv: CVCanonical,
    profile: ProfileSpec,
    bando: BandoSpec,
    budgets: Budgets,
    language: str,
    feedback: list[str] | None = None,
    previous: WriterOutput | None = None,
    subprofile: str | None = None,
) -> WriterOutput:
    user = {
        "output_language": prompts.language_name(language),
        "budgets": budgets.to_prompt_dict(),
        "tender": _profile_payload(profile, bando, subprofile),
        "cv": cv.model_dump(exclude_none=True, exclude={"source_file"}),
    }
    text = "INPUT (JSON):\n" + json.dumps(user, ensure_ascii=False)
    if feedback:
        text += (
            "\n\nREVISION REQUIRED. Your previous output had these problems; fix them while keeping everything else.\n"
            + "\n".join(f"- {f}" for f in feedback)
        )
        if previous is not None:
            text += "\n\nPREVIOUS OUTPUT (JSON):\n" + previous.model_dump_json()
    stem = cv.source_file.rsplit(".", 1)[0]
    rev = hashlib.md5("\n".join(feedback).encode("utf-8")).hexdigest()[:8] if feedback else ""
    task = f"write:{stem}" + (f":rev{rev}" if rev else "")
    out = llm.structured(
        task=task, system=prompts.WRITER_SYSTEM, user=text, schema=WriterOutput, tier="strong", max_tokens=9000
    )
    return normalize_writer_output(out, budgets)


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def normalize_writer_output(w: WriterOutput, budgets: Budgets) -> WriterOutput:
    """Pulizia strutturale deterministica (spazi, vuoti, duplicati, conteggi massimi)."""
    w = w.model_copy(deep=True)
    w.summary = _clean(w.summary)
    w.current_role = _clean(w.current_role) or None
    seen: set[str] = set()
    skills: list[str] = []
    for s in w.skills:
        s = _clean(s)
        if s and s.lower() not in seen:
            seen.add(s.lower())
            skills.append(s)
    w.skills = skills[: budgets.skills_max_items]
    w.background = [b for b in (_clean(x) for x in w.background) if b][: budgets.background_max_lines]
    blocks = []
    for e in w.experiences:
        e.title, e.role = _clean(e.title), _clean(e.role)
        e.period = _clean(e.period) or None
        e.bullets = [b for b in (_clean(x).lstrip("-•· ") for x in e.bullets) if b][: budgets.exp_bullets_per_block]
        if e.title or e.role:
            blocks.append(e)
    w.experiences = blocks[: budgets.exp_max_blocks]
    return w


def sort_blocks(blocks: list[ExperienceBlock], cv: CVCanonical) -> list[ExperienceBlock]:
    """Ordine cronologico inverso, usando le esperienze del CV da cui derivano i blocchi."""

    def key(item: tuple[int, ExperienceBlock]) -> tuple[int, int]:
        idx, b = item
        ks = [end_sort_key(cv.experiences[i]) for i in b.source_indices if 0 <= i < len(cv.experiences)]
        return (-(max(ks) if ks else -1), idx)

    return [b for _, b in sorted(enumerate(blocks), key=key)]


def _current_company(cv: CVCanonical) -> str | None:
    exps = [e for e in cv.experiences if e.company]
    if not exps:
        return None
    best = max(exps, key=end_sort_key)
    return best.company


def assemble_person(
    cv: CVCanonical,
    profile: ProfileSpec,
    w: WriterOutput,
    language: str,
    today: date | None = None,
    subprofile: str | None = None,
) -> PersonContent:
    warnings: list[str] = []
    if cv.full_name:
        name, placeholder = cv.full_name.strip(), False
    else:
        name, placeholder = invent_name(language, cv.source_file or "cv"), True
        warnings.append(f"Nome non presente nel CV '{cv.source_file}': nome inventato ('{name}').")
    months = total_months(cv, today)
    return PersonContent(
        source_file=cv.source_file,
        profile_id=profile.id,
        profile_name=profile.display_name + (f" \u2013 {subprofile}" if subprofile else ""),
        full_name=name,
        name_is_placeholder=placeholder,
        phone=cv.phone,
        email=cv.email,
        current_role=w.current_role or cv.headline,
        current_company=_current_company(cv),
        total_experience=format_experience(months, language),
        domicile=cv.location,
        summary=w.summary,
        background=w.background,
        skills=w.skills,
        experiences=sort_blocks(w.experiences, cv),
        coverage=w.coverage,
        omitted=w.omitted,
        warnings=warnings,
    )
