"""Report di generazione: tracciabilita', avvisi e gap analysis."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .content import PersonContent


class FitIssue(BaseModel):
    slide: int
    slot: str
    detail: str
    severity: str = "warning"  # warning | error


class FaithIssue(BaseModel):
    slot: str
    text: str
    reason: str
    severity: str = "medium"  # low | medium | high


class PersonReport(BaseModel):
    content: PersonContent
    fit_iterations: int = 0
    fit_issues: list[FitIssue] = Field(default_factory=list)
    fit_notes: list[str] = Field(default_factory=list, description="Riduzioni/riscritture applicate per far entrare il testo.")
    faith_issues: list[FaithIssue] = Field(default_factory=list)
    visual_notes: list[str] = Field(default_factory=list)
    slides: list[int] = Field(default_factory=list, description="Numeri (1-based) delle slide della persona nel deck.")


class GenerationReport(BaseModel):
    language: str
    template_name: str
    people: list[PersonReport] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list, description="Campi stampati dal template (vuoto = report precedente).")
    field_labels: dict[str, str] = Field(default_factory=dict, description="Etichetta leggibile dei campi personalizzati.")
