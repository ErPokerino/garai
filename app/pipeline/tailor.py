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
    instructions: str | None = None,
    hide_companies: bool = False,
) -> WriterOutput:
    user = {
        "output_language": prompts.language_name(language),
        **({"hide_company_names": True} if hide_companies else {}),
        "budgets": budgets.to_prompt_dict(),
        "tender": _profile_payload(profile, bando, subprofile),
        "cv": cv.model_dump(exclude_none=True, exclude={"source_file"}),
    }
    text = "INPUT (JSON):\n" + json.dumps(user, ensure_ascii=False)
    if instructions and instructions.strip():
        text += (
            "\n\nINSTRUCTIONS FROM THE BID MANAGER (follow them; they never allow inventing facts not in the CV):\n"
            + instructions.strip()
        )
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


def _cap(items: list, n: int, shown: bool) -> list:
    """Taglia al massimo previsto solo se il campo e' stampato dal template (altrimenti resta com'e')."""
    return items[:n] if shown and n else items


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
    w.skills = _cap(skills, budgets.skills_max_items, budgets.shows("skills"))
    w.background = _cap([b for b in (_clean(x) for x in w.background) if b], budgets.background_max_lines, budgets.shows("background"))
    blocks = []
    for e in w.experiences:
        e.title, e.role = _clean(e.title), _clean(e.role)
        e.period = _clean(e.period) or None
        e.bullets = [b for b in (_clean(x).lstrip("-•· ") for x in e.bullets) if b][: budgets.exp_bullets_per_block]
        if e.title or e.role:
            blocks.append(e)
    w.experiences = _cap(blocks, budgets.exp_max_blocks, budgets.shows("experiences"))
    extras = []
    for f in w.extra_fields:
        cf = budgets.custom_fields.get(f.key)
        if cf is None:
            continue  # campo non richiesto dal template
        f.text = _clean(f.text)
        f.items = [x for x in (_clean(i) for i in f.items) if x][: cf.get("max_items") or None]
        extras.append(f)
    w.extra_fields = extras
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
    custom_types: dict[str, str] | None = None,
    role_override: str | None = None,
    hide_companies: bool = False,
    banned_skills: set[str] | None = None,
) -> PersonContent:
    warnings: list[str] = []
    if cv.full_name and cv.full_name.strip():
        name, placeholder = cv.full_name.strip(), False
    else:
        # il nome non si inventa: resta vuoto (lo spazio nella slide resta, da completare a mano)
        name, placeholder = "", True
        warnings.append(f"Nome non presente nel CV '{cv.source_file}': lasciato vuoto, da completare.")
    months = total_months(cv, today)
    extra: dict[str, str | list[str]] = {}
    for f in w.extra_fields:
        kind = (custom_types or {}).get(f.key, "list" if f.items and not f.text else "text")
        extra[f.key] = (f.items or ([f.text] if f.text else [])) if kind == "list" else (f.text or ", ".join(f.items))
    return PersonContent(
        source_file=cv.source_file,
        profile_id=profile.id,
        profile_name=profile.display_name + (f" \u2013 {subprofile}" if subprofile else ""),
        full_name=name,
        name_is_placeholder=placeholder,
        phone=cv.phone,
        email=cv.email,
        current_role=(role_override or "").strip() or w.current_role or cv.headline,
        current_company=(w.current_company_sector or None) if hide_companies else _current_company(cv),
        total_experience=format_experience(months, language),
        domicile=cv.location,
        summary=w.summary,
        background=w.background,
        skills=[s for s in w.skills if s.casefold() not in (banned_skills or set())],
        experiences=sort_blocks(w.experiences, cv),
        extra=extra,
        coverage=w.coverage,
        omitted=w.omitted,
        warnings=warnings,
    )


# ----------------------------------------------------------------------------- riservatezza: niente nomi di aziende

_LEGAL = re.compile(
    r"\b(s\.?r\.?l\.?s?|s\.?p\.?a\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|ltd\.?|limited|inc\.?|corp\.?|gmbh|ag|plc|llc|b\.?v\.?|group|gruppo|holding)\b",
    re.I,
)
_GENERIC = {"freelance", "libero professionista", "self-employed", "self employed", "consulente", "varie", "vari", "n/a",
            "various", "confidential", "riservato", "personale", "private", "privato"}


def company_names(cv: CVCanonical) -> list[str]:
    """Nomi di aziende e clienti citati nel CV, ripuliti dalla forma societaria (es. 'ABSTRACT SRL' -> 'ABSTRACT')."""
    out: list[str] = []
    for e in cv.experiences:
        for raw in (e.company, e.client):
            for part in re.split(r"[/|,;]| - ", raw or ""):
                name = _LEGAL.sub("", part).strip(" .-&")
                if len(name) >= 3 and name.lower() not in _GENERIC and name.lower() not in [n.lower() for n in out]:
                    out.append(name)
    return sorted(out, key=len, reverse=True)


def _pattern(name: str) -> re.Pattern:
    words = [re.escape(w) for w in name.split()]
    return re.compile(r"(?<![\w])" + r"[\s\-]*".join(words) + r"(?![\w])", re.I)


def company_mentions(c: PersonContent, names: list[str]) -> list[str]:
    """Nomi di aziende ancora presenti nei testi della slide."""
    texts = [c.summary, c.current_role or "", c.current_company or "", *c.background, *c.skills]
    for e in c.experiences:
        texts += [e.title, e.role, *e.bullets]
    for v in c.extra.values():
        texts += v if isinstance(v, list) else [v]
    blob = "\n".join(t for t in texts if t)
    return [n for n in names if _pattern(n).search(blob)]


_SEP = r"[/\-–,;&]"


def _tidy(t: str) -> str:
    """Ripulisce un testo da cui e' stato tolto un nome: separatori doppi, in testa o in coda, parentesi vuote."""
    def one(m: re.Match) -> str:
        ch = m.group(0).strip()[-1]
        return {",": ", ", ";": "; "}.get(ch, f" {ch} ")

    t = re.sub(rf"\s*{_SEP}(?:\s*{_SEP})+\s*", one, t)
    t = re.sub(rf"(?:\s*{_SEP}|\s*:)+\s*$", "", t)
    t = re.sub(rf"^\s*(?:{_SEP}|:)+\s*", "", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def scrub_companies(c: PersonContent, names: list[str]) -> list[str]:
    """Ultima rete di sicurezza: toglie dai testi i nomi rimasti e ripulisce i separatori. Ritorna i nomi rimossi."""
    found = company_mentions(c, names)
    if not found:
        return []

    def clean(t: str) -> str:
        for n in found:
            t = _pattern(n).sub("", t)
        return _tidy(t)

    c.summary = clean(c.summary)
    c.current_role = clean(c.current_role) if c.current_role else c.current_role
    c.current_company = (clean(c.current_company) or None) if c.current_company else None
    c.background = [x for x in (clean(b) for b in c.background) if x]
    c.skills = [x for x in (clean(s) for s in c.skills) if x]
    for e in c.experiences:
        e.title, e.role = clean(e.title), clean(e.role)
        e.bullets = [x for x in (clean(b) for b in e.bullets) if x]
    c.extra = {k: ([x for x in (clean(i) for i in v) if x] if isinstance(v, list) else clean(v)) for k, v in c.extra.items()}
    return found
