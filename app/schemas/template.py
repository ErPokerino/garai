"""Template Spec: contratto tra analisi del template, writer LLM e motore di rendering.

Il Template Spec descrive, per ogni slide del "set persona" del template, gli slot da riempire,
la shape (o le shape) di riferimento e le opzioni di impaginazione. Per i template diversi da quello Abstract
e' proposto da un LLM con visione e poi validato/corretto in modo deterministico (app/template/normalize.py).

Nessuno slot e' obbligatorio: il motore lavora su quelli presenti. Ogni slot e' alimentato da un campo:
- campi standard di PersonContent (STANDARD_FIELDS);
- campi personalizzati dichiarati in `fields` (es. "Lingue", "Certificazioni"), scritti dal writer LLM.
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


# Campi di PersonContent che uno slot puo' usare direttamente
IDENTITY_FIELDS = ("full_name", "profile_name", "phone", "email", "current_role", "current_company",
                   "total_experience", "domicile")
WRITTEN_FIELDS = ("summary", "background", "skills", "experiences")
STANDARD_FIELDS = IDENTITY_FIELDS + WRITTEN_FIELDS


class CustomField(BaseModel):
    """Campo richiesto dal template ma non previsto dal modello standard (es. 'languages', 'certifications')."""

    key: str = Field(description="Identificativo snake_case usato dagli slot (es. 'languages').")
    description: str = Field(description="Cosa deve contenere, in inglese, per il writer (es. 'Spoken languages with level').")
    type: Literal["text", "list"] = Field(default="text", description="Testo unico oppure elenco di voci brevi.")


class SlideRef(BaseModel):
    key: str
    index: int = Field(description="Indice (0-based) della slide nel file template.")


class TemplateSpec(BaseModel):
    name: str
    template_file: str
    slides: list[SlideRef]
    font_regular: str = "assets/fonts/WorkSans-Regular.ttf"
    font_bold: str = "assets/fonts/WorkSans-Bold.ttf"
    font_family: str | None = Field(default=None, description="Font per i testi creati da zero; None = font del tema.")
    line_height_factor: float = 1.17
    bottom_limit_cm: float = Field(default=17.1, description="Limite verticale oltre cui non si deve scrivere (footer).")
    labels: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="label_key -> {lingua: testo}. Le lingue mancanti vengono tradotte via LLM."
    )
    fields: list[CustomField] = Field(default_factory=list, description="Campi personalizzati usati dagli slot.")
    slots: list[Slot]

    def slot(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.id == slot_id:
                return s
        raise KeyError(slot_id)

    def find_slot(self, slot_id: str) -> Slot | None:
        return next((s for s in self.slots if s.id == slot_id), None)

    def slots_for(self, slide_key: str) -> list[Slot]:
        return [s for s in self.slots if s.slide == slide_key]

    def custom_field(self, key: str) -> CustomField | None:
        return next((f for f in self.fields if f.key == key), None)
