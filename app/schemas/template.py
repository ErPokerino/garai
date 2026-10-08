"""Template Spec: contratto tra analisi del template, writer LLM e motore di rendering.

Il Template Spec descrive, per ogni slide del "set persona" del template, gli slot da riempire,
la shape (o le shape) di riferimento e le opzioni di impaginazione. E' un JSON validato una sola
volta da un umano (puo' essere proposto da un LLM con visione, vedi app/template/analyze_llm.py).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SlotKind = Literal[
    "static_label",  # etichetta fissa del template, tradotta nella lingua del bando
    "text",  # sostituisce il testo di una shape con un campo del contenuto
    "label_lines",  # una o piu' righe "Etichetta valore" dentro una shape
    "free_text",  # nuova casella di testo (paragrafo libero) in un'area vuota del template
    "bullets",  # nuova casella con elenco puntato, con lo stile dei bullet del template
    "pills",  # griglia di "pillole" clonate da una pillola del template
    "experience_columns",  # colonne di esperienze, ciascuna con piu' blocchi impilati
]


class Box(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Slot(BaseModel):
    id: str
    slide: str = Field(description="Chiave della slide del set persona (es. 'profile', 'experience').")
    kind: SlotKind
    field: str | None = Field(default=None, description="Campo di PersonContent che alimenta lo slot.")
    shape_ids: list[int] = Field(default_factory=list, description="Shape del template coinvolte (id originali).")
    remove_shape_ids: list[int] = Field(
        default_factory=list, description="Shape da rimuovere (segnaposto/vuote/duplicate) in ogni copia."
    )
    remove_shape_ids_if_empty: list[int] = Field(
        default_factory=list, description="Shape (es. icone/gruppi) da rimuovere se lo slot resta senza valori."
    )
    box: Box | None = Field(default=None, description="Area (cm) per gli slot che creano nuove shape.")
    font_pt: float | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class SlideRef(BaseModel):
    key: str
    index: int = Field(description="Indice (0-based) della slide nel file template.")


class TemplateSpec(BaseModel):
    name: str
    template_file: str
    slides: list[SlideRef]
    font_regular: str = "assets/fonts/WorkSans-Regular.ttf"
    font_bold: str = "assets/fonts/WorkSans-Bold.ttf"
    line_height_factor: float = 1.17
    bottom_limit_cm: float = Field(default=17.1, description="Limite verticale oltre cui non si deve scrivere (footer).")
    labels: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="label_key -> {lingua: testo}. Le lingue mancanti vengono tradotte via LLM."
    )
    slots: list[Slot]

    def slot(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.id == slot_id:
                return s
        raise KeyError(slot_id)

    def slots_for(self, slide_key: str) -> list[Slot]:
        return [s for s in self.slots if s.slide == slide_key]
