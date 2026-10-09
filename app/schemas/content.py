"""Contenuto finale (gia' riassunto/riordinato) pronto per essere inserito negli slot del template."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExperienceBlock(BaseModel):
    title: str = Field(description="Intestazione del blocco: 'Settore/Cliente – Nome progetto'.")
    role: str = Field(description="Ruolo ricoperto in questa esperienza.")
    period: str | None = Field(default=None, description="Periodo, es. '03/2023 – oggi'.")
    bullets: list[str] = Field(default_factory=list, description="Attivita' svolte e competenze utilizzate.")
    source_indices: list[int] = Field(
        default_factory=list,
        description="Indici (0-based) delle esperienze del CV canonico da cui deriva il blocco.",
    )


class RequirementCoverage(BaseModel):
    requirement: str
    status: str = Field(description="'met', 'partial' oppure 'not_evidenced'.")
    evidence: str = Field(default="", description="Riferimento sintetico al CV che supporta lo stato.")


class ExtraField(BaseModel):
    """Valore di un campo personalizzato richiesto dal template."""

    key: str = Field(description="Chiave del campo, esattamente come in budgets.custom_fields.")
    text: str = Field(default="", description="Valore per i campi di tipo 'text'.")
    items: list[str] = Field(default_factory=list, description="Voci per i campi di tipo 'list'.")


class WriterOutput(BaseModel):
    """Cio' che produce il Writer LLM (solo le parti creative/di sintesi)."""

    current_role: str | None = Field(default=None, description="Ruolo attuale, nella lingua di output.")
    summary: str = Field(default="", description="Profilo sintetico orientato al ruolo richiesto.")
    background: list[str] = Field(
        default_factory=list, description="Formazione, certificazioni e lingue, una riga per voce, in ordine di rilevanza."
    )
    skills: list[str] = Field(default_factory=list, description="Competenze chiave, etichette brevi, le piu' rilevanti per il bando per prime.")
    experiences: list[ExperienceBlock] = Field(default_factory=list, description="Esperienze selezionate e riassunte.")
    extra_fields: list[ExtraField] = Field(
        default_factory=list, description="Valori dei campi personalizzati del template (budgets.custom_fields)."
    )
    coverage: list[RequirementCoverage] = Field(
        default_factory=list, description="Copertura dei requisiti minimi/premianti del profilo."
    )
    omitted: list[str] = Field(default_factory=list, description="Elementi rilevanti del CV lasciati fuori per spazio.")


class PersonContent(BaseModel):
    """Contenuto completo di una persona (identita' deterministica + testi del Writer)."""

    source_file: str
    profile_id: str
    profile_name: str
    full_name: str
    name_is_placeholder: bool = False
    phone: str | None = None
    email: str | None = None
    current_role: str | None = None
    current_company: str | None = None
    total_experience: str | None = None
    domicile: str | None = None
    summary: str = ""
    background: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experiences: list[ExperienceBlock] = Field(default_factory=list)
    extra: dict[str, str | list[str]] = Field(default_factory=dict, description="Campi personalizzati del template.")
    coverage: list[RequirementCoverage] = Field(default_factory=list)
    omitted: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
