"""Report leggibile (Markdown) della generazione: assegnazioni, gap analysis, avvisi, modifiche per il fit."""
from __future__ import annotations

from app.schemas import GenerationReport

STATUS = {"met": "OK", "partial": "PARZIALE", "not_evidenced": "NON EVIDENZIATO"}


def to_markdown(r: GenerationReport) -> str:
    out = [f"# Report di generazione", "", f"- Lingua di output: **{r.language}**", f"- Template: {r.template_name}"]
    for n in r.notes:
        out.append(f"- {n}")
    for pr in r.people:
        c = pr.content
        out += ["", f"## {c.full_name or 'Nome mancante'} ({c.source_file})", ""]
        out.append(f"- Profilo proposto: **{c.profile_name}** (id {c.profile_id})")
        if c.name_is_placeholder:
            out.append("- ATTENZIONE: nome non presente nel CV, **lasciato vuoto** (da completare)")
        for w in c.warnings:
            out.append(f"- {w}")
        out.append(f"- Iterazioni di fit: {pr.fit_iterations}")
        out += [f"- {n}" for n in pr.fit_notes]
        if pr.fit_issues:
            out.append("- Problemi di impaginazione residui:")
            out += [f"  - slide {i.slide} [{i.slot}] {i.detail}" for i in pr.fit_issues]
        if pr.faith_issues:
            out.append("- Verifica di fedelta' (affermazioni non supportate dal CV):")
            out += [f"  - ({i.severity}) [{i.slot}] {i.text} -> {i.reason}" for i in pr.faith_issues]
        if pr.visual_notes:
            out.append("- Note del critico visivo:")
            out += [f"  - {n}" for n in pr.visual_notes]
        if c.coverage:
            out += ["", "Copertura dei requisiti:", ""]
            out += [f"- [{STATUS.get(x.status, x.status)}] {x.requirement} - {x.evidence}" for x in c.coverage]
        if c.omitted:
            out += ["", "Lasciato fuori per spazio: " + "; ".join(c.omitted)]
    return "\n".join(out) + "\n"
