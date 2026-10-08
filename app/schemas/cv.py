"""Schema canonico di un CV, indipendente dal formato di origine."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CVExperience(BaseModel):
    company: str | None = Field(default=None, description="Datore di lavoro / societa' presso cui lavora.")
    role: str | None = Field(default=None, description="Ruolo ricoperto.")
    client: str | None = Field(default=None, description="Cliente finale, se indicato.")
    project: str | None = Field(default=None, description="Nome del progetto, se indicato.")
    industry: str | None = Field(default=None, description="Settore (es. Energy, Fashion, Banking) se desumibile.")
    start: str | None = Field(default=None, description="Inizio, formato YYYY-MM (o YYYY).")
    end: str | None = Field(default=None, description="Fine, formato YYYY-MM (o YYYY); null se in corso.")
    is_current: bool = Field(default=False, description="True se l'esperienza e' in corso.")
    description: str = Field(default="", description="Descrizione sintetica fedele al CV.")
    activities: list[str] = Field(default_factory=list, description="Attivita' svolte, una per voce.")
    technologies: list[str] = Field(default_factory=list, description="Tecnologie/strumenti citati.")


class CVEducation(BaseModel):
    degree: str
    institution: str | None = None
    period: str | None = Field(default=None, description="Periodo o anno come nel CV.")
    grade: str | None = None


class CVLanguage(BaseModel):
    language: str
    level: str | None = None


class CVCanonical(BaseModel):
    source_file: str = ""
    full_name: str | None = Field(default=None, description="Nome e cognome SOLO se presenti nel CV, altrimenti null.")
    email: str | None = None
    phone: str | None = None
    location: str | None = Field(default=None, description="Citta' di domicilio/residenza se indicata.")
    headline: str | None = Field(default=None, description="Ruolo/qualifica attuale dichiarata nel CV.")
    experiences: list[CVExperience] = Field(default_factory=list)
    education: list[CVEducation] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[CVLanguage] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="Competenze tecniche/trasversali esplicite.")
    other: list[str] = Field(default_factory=list, description="Altre informazioni rilevanti (es. pubblicazioni).")
