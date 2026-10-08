"""Ciclo di fit: costruzione deck -> misura sul rendering reale -> correzione (writer LLM, poi trimming deterministico)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.render.base import issues_from_measures
from app.schemas import FitIssue, PersonContent, TemplateSpec
from app.template.budget import Budgets
from app.template.deck import DeckResult, build_deck, experience_capacity

# ----------------------------------------------------------------------------- pre-check sui budget


def budget_feedback(c: PersonContent, b: Budgets) -> list[str]:
    """Violazioni dei budget (stima rapida) formulate come istruzioni per il writer."""
    fb: list[str] = []
    if len(c.summary) > b.summary_max_chars:
        fb.append(f"summary has {len(c.summary)} chars, must be <= {b.summary_max_chars}")
    if len(c.skills) > b.skills_max_items:
        fb.append(f"skills has {len(c.skills)} items, must be <= {b.skills_max_items}")
    for s in c.skills:
        if len(s) > b.skills_max_chars:
            fb.append(f"skill '{s}' has {len(s)} chars, must be <= {b.skills_max_chars}")
    if len(c.background) > b.background_max_lines:
        fb.append(f"background has {len(c.background)} lines, must be <= {b.background_max_lines}")
    if len(c.experiences) > b.exp_max_blocks:
        fb.append(f"experiences has {len(c.experiences)} blocks, must be <= {b.exp_max_blocks}")
    for i, e in enumerate(c.experiences):
        if len(e.title) > b.exp_title_chars:
            fb.append(f"experience #{i + 1} title has {len(e.title)} chars, must be <= {b.exp_title_chars}")
        role_len = len(e.role) + (len(e.period) + 3 if e.period else 0)
        if role_len > b.exp_role_chars:
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
            if len(x) > b.exp_bullet_chars:
                fb.append(f"experience #{i + 1} bullet #{j + 1} has {len(x)} chars, must be <= {b.exp_bullet_chars}")
    return fb


# ----------------------------------------------------------------------------- trimming deterministico


def _drop_last_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(parts) > 1:
        return " ".join(parts[:-1])
    cut = text[: int(len(text) * 0.85)].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "."


def trim_for_issue(
    c: PersonContent, slot: str, extra: str, chunk_idx: int, n_cols: int, cap: int
) -> str | None:
    """Applica la piu' piccola riduzione sensata per risolvere l'issue. Ritorna una nota o None se non risolvibile."""
    if slot == "experiences" and extra.startswith("c"):
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
    if slot == "summary":
        c.summary = _drop_last_sentence(c.summary)
        return "sintesi accorciata per spazio"
    if slot == "background" and len(c.background) > 1:
        removed = c.background.pop()
        return f"formazione: rimossa voce '{removed[:40]}'"
    if slot == "skills" and extra.isdigit() and int(extra) < len(c.skills):
        removed = c.skills.pop(int(extra))
        return f"competenza '{removed}' rimossa (non entra nella pillola)"
    if slot == "name":
        toks = c.full_name.split()
        if len(toks) > 2:
            c.full_name = f"{toks[0]} {toks[-1]}"
            return "nome abbreviato (nome + cognome)"
    if slot == "role_company":
        if c.current_role and len(c.current_role) > 24:
            c.current_role = c.current_role[:23].rsplit(" ", 1)[0]
            return "ruolo attuale abbreviato"
        if c.current_company and len(c.current_company) > 20:
            c.current_company = c.current_company[:19].rsplit(" ", 1)[0]
            return "azienda abbreviata"
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
    ex = spec.slot("experiences")
    n_cols = len(ex.shape_ids)
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
                note = trim_for_issue(c, issue.slot, extra, chunk_idx, n_cols, cap)
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
