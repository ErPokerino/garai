"""Schemi di supporto per le chiamate LLM minori."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas import FaithIssue


class GeneralRequirements(BaseModel):
    title: str = ""
    requirements: list[str] = Field(default_factory=list)


class Assignment(BaseModel):
    profile_id: str
    subprofile: str | None = Field(
        default=None, description="Nome ESATTO della variante (subprofile) scelta, se il profilo ne ha; altrimenti null."
    )
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""


class VerifyResult(BaseModel):
    issues: list[FaithIssue] = Field(default_factory=list)


class CriticResult(BaseModel):
    notes: list[str] = Field(default_factory=list)


class LabelPair(BaseModel):
    key: str
    text: str


class Translation(BaseModel):
    # lista di coppie e non dict: gli schemi "mappa" non sono supportati allo stesso modo da tutti i provider
    items: list[LabelPair] = Field(default_factory=list)
