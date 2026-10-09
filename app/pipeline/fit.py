"""Ciclo di fit: costruzione deck -> misura sul rendering reale -> correzione (writer LLM, poi trimming deterministico)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.render.base import issues_from_measures
from app.schemas import STANDARD_FIELDS, FitIssue, PersonContent, TemplateSpec
from app.template.budget import Budgets
from app.template.deck import DeckResult, build_deck, experience_capacity, experience_columns_slot
from app.template.fill import field_value

# ----------------------------------------------------------------------------- pre-check sui budget


def budget_feedback(c: PersonContent, b: Budgets) -> list[str]:
    """Violazioni dei budget (stima rapida) formulate come istruzioni per il writer. Solo i campi stampati dal template."""
    fb: list[str] = []
    if b.shows("summary") and b.summary_max_chars and len(c.summary) > b.summary_max_chars:
        fb.append(f"summary has {len(c.summary)} chars, must be <= {b.summary_max_chars}")
    if b.shows("skills") and b.skills_max_items:
        if len(c.skills) > b.skills_max_items:
            fb.append(f"skills has {len(c.skills)} items, must be <= {b.skills_max_items}")
        for s in c.skills:
            if b.skills_max_chars and len(s) > b.skills_max_chars:
                fb.append(f"skill '{s}' has {len(s)} chars, must be <= {b.skills_max_chars}")
    if b.shows("background") and b.background_max_lines and len(c.background) > b.background_max_lines:
        fb.append(f"background has {len(c.background)} lines, must be <= {b.background_max_lines}")
    if b.shows("experiences") and b.exp_max_blocks:
        if len(c.experiences) > b.exp_max_blocks:
            fb.append(f"experiences has {len(c.experiences)} blocks, must be <= {b.exp_max_blocks}")
        for i, e in enumerate(c.experiences):
            if b.exp_title_chars and len(e.title) > b.exp_title_chars:
                fb.append(f"experience #{i + 1} title has {len(e.title)} chars, must be <= {b.exp_title_chars}")
            role_len = len(e.role) + (len(e.period) + 3 if e.period else 0)
            if b.exp_role_chars and role_len > b.exp_role_chars:
                fb.append(f"experience #{i + 1} role+period has {role_len} chars, must be <= {b.exp_role_chars}")
            if len(e.bullets) > b.exp_bullets_per_block:
                fb.append(f"experience #{i + 1} has {len(e.bullets)} bullets, must be <= {b.exp_bullets_per_block}")
            lines = sum(max(1, -(-len(x) // max(1, b.exp_bullet_chars // 2))) for x in e.bullets)
            if lines > b.exp_bullet_lines_total:
                fb.append(
                    f"experience #{i + 1} bullets need ~{lines} lines, must be <= {b.exp_bullet_lines_total} "
                    f"(shorten bullets to ~{b.exp_bullet_chars // 2} chars per line)"
                )
            for j, x in enumerate(e.bullets):
                if b.exp_bullet_chars and len(x) > b.exp_bullet_chars:
                    fb.append(f"experience #{i + 1} bullet #{j + 1} has {len(x)} chars, must be <= {b.exp_bullet_chars}")
    for key, cf in b.custom_fields.items():
        v = c.extra.get(key)
        if isinstance(v, list) and cf.get("max_items") and len(v) > cf["max_items"]:
            fb.append(f"custom field '{key}' has {len(v)} items, must be <= {cf['max_items']}")
        elif isinstance(v, str) and cf.get("max_chars") and len(v) > cf["max_chars"]:
            fb.append(f"custom field '{key}' has {len(v)} chars, must be <= {cf['max_chars']}")
    return fb


# ----------------------------------------------------------------------------- trimming deterministico

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _drop_last_sentence(text: str) -> str:
    parts = _SENTENCE.split(text.strip())
    if len(parts) > 1:
        return " ".join(parts[:-1])
    cut = text[: int(len(text) * 0.85)].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "."


def _shorten_value(v: str) -> str:
    cut = v[: max(1, int(len(v) * 0.85))].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…" if cut and cut != v else v


def _trim_experiences_list(c: PersonContent) -> str | None:
    if not c.experiences:
        return None
    cand = max(range(len(c.experiences)), key=lambda i: (len(c.experiences[i].bullets), i))
    blk = c.experiences[cand]
    if len(blk.bullets) > 1:
        dropped = blk.bullets.pop()
        return f"ridotto per spazio: rimosso ultimo punto di '{blk.title}' ({dropped[:40]}...)"
    if len(c.experiences) == 1:
        return None
    removed = c.experiences.pop()
    return f"ridotto per spazio: rimossa esperienza '{removed.title}'"


def _trim_field(c: PersonContent, name: str, extra: str, n_items: int = 1) -> str | None:
    """Riduzione di un campo qualsiasi: lista -> ultima voce (o quella indicata), testo -> ultima frase."""
    if name == "experiences":
        return _trim_experiences_list(c)
    if name == "full_name":
        toks = c.full_name.split()
        if len(toks) > 2:
            c.full_name = f"{toks[0]} {toks[-1]}"
            return "nome abbreviato (nome + cognome)"
        return None
    v = field_value(c, name)

    def setter(nv) -> None:
        if name in STANDARD_FIELDS:
            setattr(c, name, nv)
        else:
            c.extra[name] = nv

    if isinstance(v, list) and v:
        if extra.isdigit() and int(extra) < len(v):
            removed = v.pop(int(extra))
            return f"{name}: rimossa voce '{str(removed)[:40]}' per spazio"
        keep = max(1, len(v) - n_items)
        if keep >= len(v):
            return None
        removed = v[keep:]
        del v[keep:]
        what = f"'{str(removed[0])[:40]}'" if len(removed) == 1 else f"{len(removed)} voci"
        return f"{name}: rimoss{'a' if len(removed) == 1 else 'e'} {what} per spazio"
    if isinstance(v, str) and v:
        nv = _drop_last_sentence(v) if len(_SENTENCE.split(v.strip())) > 1 or len(v) > 60 else _shorten_value(v)
        if nv == v:
            return None
        setter(nv)
        return f"{name}: testo accorciato per spazio"
    return None


def trim_for_issue(
    c: PersonContent, spec: TemplateSpec, slot_id: str, extra: str, chunk_idx: int, n_cols: int, cap: int,
    over_pt: float = 0.0,
) -> str | None:
    """Applica la piu' piccola riduzione sensata per risolvere l'issue. Ritorna una nota o None se non risolvibile.
    over_pt: quanto testo eccede (pt); negli elenchi si tolgono circa meta' delle righe in eccesso per passata."""
    slot = spec.find_slot(slot_id)
    if slot is None:
        return None
    line_pt = (slot.font_pt or 11) * spec.line_height_factor
    n_items = max(1, int(over_pt / line_pt / 2))
    if slot.kind == "experience_columns" and extra.startswith("c"):
        col = int(extra[1:])
        start = chunk_idx * cap
        idxs = [i for i in range(start, min(start + cap, len(c.experiences))) if (i - start) % n_cols == col]
        if not idxs:
            return None
        cand = max(idxs, key=lambda i: (len(c.experiences[i].bullets), sum(len(x) for x in c.experiences[i].bullets)))
        blk = c.experiences[cand]
        if len(blk.bullets) > 1:
            dropped = blk.bullets.pop()
            return f"ridotto per spazio: rimosso ultimo punto di '{blk.title}' ({dropped[:40]}...)"
        last = idxs[-1]
        removed = c.experiences.pop(last)
        return f"ridotto per spazio: rimossa esperienza '{removed.title}'"
    if slot.kind == "label_lines":
        # la riga piu' lunga tra quelle compilate perde un po' di testo
        names = [ln.get("field") for ln in slot.options.get("lines", []) if ln.get("field")]
        vals = [(n, field_value(c, n)) for n in names]
        vals = [(n, v) for n, v in vals if isinstance(v, str) and v]
        if not vals:
            return None
        n, v = max(vals, key=lambda nv: len(nv[1]))
        if n == "full_name":
            return _trim_field(c, n, "")
        nv = _shorten_value(v)
        if nv == v:
            return None
        if n in STANDARD_FIELDS:
            setattr(c, n, nv)
        else:
            c.extra[n] = nv
        return f"{n}: valore abbreviato per spazio"
    if slot.field:
        return _trim_field(c, slot.field, extra, n_items)
    return None


# ----------------------------------------------------------------------------- loop


@dataclass
class FitResult:
    deck: DeckResult
    iterations: int
    remaining: dict[int, list[FitIssue]] = field(default_factory=dict)  # persona -> issue non risolte
    notes: dict[int, list[str]] = field(default_factory=dict)  # persona -> modifiche applicate


Rewriter = Callable[[int, list[str]], PersonContent | None]


def fit_deck(
    spec: TemplateSpec,
    contents: list[PersonContent],
    labels: dict[str, str],
    language: str,
    out_path: Path,
    renderer,
    rewriter: Rewriter | None = None,
    max_llm_iterations: int = 2,
    max_trim_passes: int = 12,
) -> FitResult:
    ex = experience_columns_slot(spec)
    n_cols = len(ex.shape_ids) if ex is not None else 1
    cap = experience_capacity(spec)
    notes: dict[int, list[str]] = {i: [] for i in range(len(contents))}
    iteration = 0
    deck = build_deck(spec, contents, labels, language, out_path)
    remaining: dict[int, list[FitIssue]] = {}

    for iteration in range(1, max_llm_iterations + max_trim_passes + 1):
        found = issues_from_measures(renderer.measure(deck.path))
        if not found:
            remaining = {}
            break
        by_person: dict[int, list] = {}
        for person, issue, over, extra in found:
            by_person.setdefault(person, []).append((issue, over, extra))

        changed = False
        remaining = {p: [it[0] for it in items] for p, items in by_person.items()}
        for person, items in by_person.items():
            c = contents[person]
            if rewriter is not None and iteration <= max_llm_iterations:
                fb = [
                    f"{issue.detail} (slide {issue.slide}); shorten the text of '{issue.slot}' so it physically fits"
                    for issue, _, _ in items
                ]
                new = rewriter(person, fb)
                if new is not None:
                    contents[person] = new
                    notes[person].append(f"riscrittura LLM per fit (iterazione {iteration}): " + "; ".join(i.detail for i, _, _ in items))
                    changed = True
                    continue
            # trimming deterministico: una riduzione per issue e per passata
            for issue, over, extra in items:
                chunk_idx = next(
                    (s.chunk for s in deck.slides if s.slide_no == issue.slide and s.person_idx == person), 0
                )
                note = trim_for_issue(c, spec, issue.slot, extra, chunk_idx, n_cols, cap, over_pt=over)
                if note:
                    notes[person].append(note)
                    changed = True
        if not changed:
            break
        deck = build_deck(spec, contents, labels, language, out_path)
    else:
        # esauriti i tentativi: ricontrolla lo stato finale
        found = issues_from_measures(renderer.measure(deck.path))
        remaining = {}
        for person, issue, _, _ in found:
            remaining.setdefault(person, []).append(issue)

    if remaining:
        # ultima verifica dopo l'ultima modifica
        found = issues_from_measures(renderer.measure(deck.path))
        remaining = {}
        for person, issue, _, _ in found:
            remaining.setdefault(person, []).append(issue)
    return FitResult(deck=deck, iterations=iteration, remaining=remaining, notes=notes)
