"""Interfaccia dei renderer (PPTX -> immagini) e controllo overflow sul rendering reale."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.schemas import FitIssue


@dataclass
class ShapeMeasure:
    slide_no: int
    name: str
    shape_top_pt: float
    shape_height_pt: float
    text_top_pt: float
    text_height_pt: float
    n_lines: int
    font_pt: float | None = None


class Renderer(Protocol):
    name: str

    def render(self, pptx_path: Path, out_dir: Path, width_px: int = 1600) -> list[Path]: ...

    def measure(self, pptx_path: Path) -> list[ShapeMeasure]: ...

    def close(self) -> None: ...


def parse_name(name: str) -> tuple[str, int, str, str | None]:
    """'slot:<id>:<persona>[:extra]|chk=<regola>' -> (slot_id, persona, extra, chk)."""
    base, _, chk = name.partition("|chk=")
    parts = base.split(":")
    slot_id = parts[1]
    person = int(parts[2])
    extra = parts[3] if len(parts) > 3 else ""
    return slot_id, person, extra, (chk or None)


def issues_from_measures(measures: list[ShapeMeasure], tolerance_pt: float = 1.5) -> list[tuple[int, FitIssue, int, str]]:
    """Confronta il testo reale con le shape marcate. Ritorna (persona, issue, over_pt, extra)."""
    out: list[tuple[int, FitIssue, int, str]] = []
    for m in measures:
        if not m.name.startswith("slot:") or "|chk=" not in m.name:
            continue
        slot_id, person, extra, chk = parse_name(m.name)
        if chk == "h":
            over = (m.text_top_pt + m.text_height_pt) - (m.shape_top_pt + m.shape_height_pt)
            if over > tolerance_pt:
                out.append(
                    (
                        person,
                        FitIssue(
                            slide=m.slide_no,
                            slot=slot_id,
                            detail=f"{extra or slot_id}: testo oltre il bordo di {over:.0f}pt",
                            severity="error",
                        ),
                        int(round(over)),
                        extra,
                    )
                )
        elif chk and chk.startswith("lines:"):
            expected = int(chk.split(":")[1])
            if m.n_lines > expected:
                out.append(
                    (
                        person,
                        FitIssue(
                            slide=m.slide_no,
                            slot=slot_id,
                            detail=f"{extra or slot_id}: {m.n_lines} righe invece di {expected}",
                            severity="error",
                        ),
                        m.n_lines - expected,
                        extra,
                    )
                )
    return out
