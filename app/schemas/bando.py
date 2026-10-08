"""Schema strutturato del bando: profili professionali e requisiti."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SubProfile(BaseModel):
    """Variante di un profilo (es. per piattaforma: CMS, App Mobile, Web) con requisiti propri."""

    name: str = Field(description="Etichetta breve della variante, es. 'Applicazione Web' o 'Web Application'.")
    min_requirements: list[str] = Field(default_factory=list, description="Requisiti minimi specifici della variante.")
    preferred: list[str] = Field(
        default_factory=list, description="Elementi premianti specifici (con cluster di priorita' se presenti, es. 'P1: ...')."
    )
    certifications: list[str] = Field(default_factory=list)


class ProfileSpec(BaseModel):
    """Un profilo professionale richiesto dal bando."""

    id: str = Field(description="Identificativo breve e stabile, es. '3.2' oppure 'project-manager'.")
    name: str = Field(description="Nome del ruolo come scritto nel bando, es. 'Project Manager'.")
    name_local: str | None = Field(
        default=None,
        description="Nome del ruolo nella lingua del bando se il bando riporta una traduzione tra parentesi.",
    )
    purpose: str = Field(default="", description="Descrizione sintetica dello scopo del ruolo (1-2 frasi).")
    responsibilities: list[str] = Field(default_factory=list, description="Principali responsabilita'.")
    skills_required: list[str] = Field(
        default_factory=list, description="Competenze specifiche della piattaforma/servizio richieste."
    )
    min_requirements: list[str] = Field(
        default_factory=list,
        description="Requisiti minimi di idoneita' del CV (titoli, anni di esperienza, campi di conoscenza, lingue).",
    )
    preferred: list[str] = Field(default_factory=list, description="Elementi premianti.")
    certifications: list[str] = Field(default_factory=list, description="Certificazioni citate (richieste o premianti).")
    subprofiles: list[SubProfile] = Field(
        default_factory=list,
        description="Varianti del profilo con requisiti minimi/premianti propri (se il bando le prevede).",
    )
    min_years_total: int | None = Field(default=None, description="Anni minimi di esperienza complessiva, se indicati.")
    min_years_role: int | None = Field(default=None, description="Anni minimi nel ruolo proposto, se indicati.")

    @property
    def display_name(self) -> str:
        return self.name_local or self.name


class BandoSpec(BaseModel):
    language: str = Field(default="it", description="Codice lingua ISO 639-1 del bando (it, en, es, ...).")
    title: str = ""
    general_requirements: list[str] = Field(
        default_factory=list, description="Requisiti trasversali validi per tutte le risorse."
    )
    profiles: list[ProfileSpec] = Field(default_factory=list)

    def get(self, profile_id: str) -> ProfileSpec | None:
        for p in self.profiles:
            if p.id == profile_id:
                return p
        return None
