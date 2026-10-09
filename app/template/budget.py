"""Budget di testo per campo, calcolati dalla geometria reale del template e dai font.

Il calcolo non dipende dai nomi degli slot ne' dal template Abstract: per ogni campo si guarda in quale slot
compare, con quale tipo di impaginazione (paragrafo, elenco, pillole, colonne di esperienze) e quanto spazio ha.
I campi che il template non mostra hanno budget 0 e non vanno scritti.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from pptx import Presentation

from app.schemas import STANDARD_FIELDS, Slot, TemplateSpec

from .geometry import cm, slide_of, slot_area
from .measure import CM_TO_PT, TextMeter
from .spec import template_path
from .xmlutil import shape_by_id

INSET_CM = 0.1  # 36000 EMU di margine nelle colonne esperienza
BULLET_INDENT_CM = 0.5  # marL 179388 EMU
PILL_INSET_CM = 0.3  # 108000 EMU per lato
SUB_INDENT_CM = 1.0  # rientro dei sotto-punti delle esperienze in un elenco


@dataclass
class ColumnGeom:
    shape_id: int
    x: float
    y: float
    w: float  # cm (larghezza totale shape)
    usable_h: float  # cm fino al limite inferiore


@dataclass
class Budgets:
    summary_max_lines: int = 0
    summary_max_chars: int = 0
    background_max_lines: int = 0
    background_line_chars: int = 0
    skills_max_items: int = 0
    skills_max_chars: int = 0
    role_company_max_chars: int = 44
    exp_max_blocks: int = 0
    exp_blocks_per_column: int = 2
    exp_title_chars: int = 0
    exp_role_chars: int = 0
    exp_bullets_per_block: int = 4
    exp_bullet_chars: int = 0
    exp_bullet_lines_total: int = 0
    # campi effettivamente stampati dal template: gli altri vanno lasciati vuoti
    fields_on_template: list[str] = field(default_factory=list)
    # campi personalizzati: chiave -> {description, type, max_chars | max_items + item_chars}
    custom_fields: dict[str, dict] = field(default_factory=dict)
    columns: list[ColumnGeom] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        d = asdict(self)
        d.pop("columns", None)
        if not d["custom_fields"]:
            d.pop("custom_fields")
        return d

    def shows(self, name: str) -> bool:
        return name in self.fields_on_template


def slot_fields(slot: Slot) -> list[str]:
    """Campi letti da uno slot (label_lines ne legge uno per riga)."""
    if slot.kind == "label_lines":
        return [ln.get("field") for ln in slot.options.get("lines", []) if ln.get("field")]
    return [slot.field] if slot.field else []


def _font_pt(slot: Slot, default: float) -> float:
    return float(slot.font_pt or default)


def _lines_chars(meter: TextMeter, w: float, h: float, pt: float, indent: float = 0.0, space_after: float = 0.0) -> tuple[int, int]:
    line_h = meter.line_height_pt(pt) + space_after
    lines = max(1, int(h * CM_TO_PT / line_h))
    return lines, max(8, meter.chars_per_line(w, pt, indent_cm=indent))


def _columns_budget(b: Budgets, prs, spec: TemplateSpec, slot: Slot, meter: TextMeter, max_experiences: int) -> None:
    slide = slide_of(prs, spec, slot)
    pt = _font_pt(slot, 10)
    limit = spec.bottom_limit_cm
    for sid in slot.shape_ids:
        sh = shape_by_id(slide, sid)
        if sh is None:
            continue
        top = cm(sh.top)
        width = slot.options.get("column_width_cm") or cm(sh.width)
        b.columns.append(ColumnGeom(sid, cm(sh.left), top, width, usable_h=limit - top - 2 * INSET_CM))
    if not b.columns:
        return
    bpc = int(slot.options.get("blocks_per_column", 2))
    b.exp_blocks_per_column = bpc
    b.exp_max_blocks = min(max_experiences, len(b.columns) * bpc)
    b.exp_bullets_per_block = int(slot.options.get("bullets_per_block", 4))
    min_text_w = min(c.w for c in b.columns) - 2 * INSET_CM
    col_lines = min(meter.max_lines(c.usable_h, pt) for c in b.columns)
    block_lines = (col_lines - (bpc - 1)) // bpc
    title_lines, role_lines, blank_lines = 1, 2, 1
    b.exp_bullet_lines_total = max(2, block_lines - title_lines - role_lines - blank_lines)
    b.exp_title_chars = int(meter.chars_per_line(min_text_w, pt, bold=True) * title_lines * 0.95)
    b.exp_role_chars = int(meter.chars_per_line(min_text_w, pt) * role_lines * 0.9)
    b.exp_bullet_chars = int(meter.chars_per_line(min_text_w, pt, indent_cm=BULLET_INDENT_CM) * 2 * 0.92)


def _list_experiences_budget(b: Budgets, w: float, h: float, pt: float, meter: TextMeter, max_experiences: int) -> None:
    """Esperienze in un elenco: per ognuna una riga di intestazione (titolo – ruolo, periodo) e sotto-punti."""
    lines, cpl = _lines_chars(meter, w, h, pt, indent=BULLET_INDENT_CM, space_after=2)
    blocks = max(1, min(max_experiences, lines // 4))
    per_block = max(2, lines // blocks)
    b.exp_max_blocks = blocks
    b.exp_blocks_per_column = blocks
    b.exp_title_chars = int(cpl * 0.55)
    b.exp_role_chars = int(cpl * 0.4)
    b.exp_bullets_per_block = max(1, min(4, per_block - 1))
    sub_cpl = meter.chars_per_line(w, pt, indent_cm=SUB_INDENT_CM)
    b.exp_bullet_lines_total = max(1, per_block - 1)
    b.exp_bullet_chars = int(sub_cpl * 1.8)


def compute_budgets(spec: TemplateSpec, meter: TextMeter, max_experiences: int = 6) -> Budgets:
    prs = Presentation(str(template_path(spec)))
    b = Budgets()
    shown: list[str] = []

    for slot in spec.slots:
        if slot.kind == "static_label":
            continue
        names = slot_fields(slot)
        shown += [n for n in names if n not in shown]
        if slot.kind == "experience_columns":
            _columns_budget(b, prs, spec, slot, meter, max_experiences)
            continue
        area = slot_area(prs, spec, slot)
        if area is None:
            continue
        pt = _font_pt(slot, 11)
        space_after = float(slot.options.get("space_after_pt", 0))
        for name in names:
            if slot.kind == "label_lines":
                # una riga: etichetta + valore; il valore ha circa la larghezza della riga meno l'etichetta
                cpl = max(8, int(meter.chars_per_line(area.w, pt) * 0.75))
                if name == "current_role":
                    b.role_company_max_chars = int(slot.options.get("max_chars", cpl))
                _custom_budget(b, spec, name, max_chars=cpl, max_items=4, item_chars=max(8, cpl // 3))
                continue
            single = slot.kind == "text"
            text_lines = int(slot.options.get("max_lines", 1)) if single else None
            if slot.kind == "pills":
                cols = slot.options.get("columns") or []
                rows = int(slot.options.get("max_rows", 1))
                if cols:
                    b.skills_max_items = len(cols) * rows
                    min_w = min(c["w"] for c in cols)
                    b.skills_max_chars = int(meter.chars_per_line(min_w, pt, indent_cm=2 * PILL_INSET_CM) * 0.95)
                continue
            indent = BULLET_INDENT_CM if slot.kind == "bullets" else 0.0
            # voci di elenco di 1-2 righe: lo spazio dopo ogni voce pesa circa mezza volta per riga
            gap = space_after * 0.5 if slot.kind == "bullets" else space_after
            lines, cpl = _lines_chars(meter, area.w, area.h, pt, indent=indent, space_after=gap)
            if text_lines:
                lines = text_lines
            if name == "summary":
                b.summary_max_lines = lines
                b.summary_max_chars = int(lines * cpl * 0.92)
            elif name == "background":
                b.background_max_lines = lines
                b.background_line_chars = cpl
            elif name == "skills":
                if slot.kind == "bullets":
                    b.skills_max_items, b.skills_max_chars = lines, int(cpl * 0.95)
                else:  # elenco separato da virgole in un paragrafo
                    b.skills_max_items, b.skills_max_chars = max(3, int(lines * cpl * 0.9 / 18)), 28
            elif name == "experiences":
                _list_experiences_budget(b, area.w, area.h, pt, meter, max_experiences)
            elif name not in STANDARD_FIELDS:
                _custom_budget(b, spec, name, max_chars=int(lines * cpl * 0.92), max_items=lines, item_chars=int(cpl * 0.95))
    b.fields_on_template = shown
    return b


def _custom_budget(b: Budgets, spec: TemplateSpec, name: str, *, max_chars: int, max_items: int, item_chars: int) -> None:
    if name in STANDARD_FIELDS:
        return
    cf = spec.custom_field(name)
    kind = cf.type if cf else "text"
    entry = {"description": cf.description if cf else name.replace("_", " "), "type": kind}
    if kind == "list":
        entry.update(max_items=max_items, item_chars=item_chars)
    else:
        entry.update(max_chars=max_chars)
    b.custom_fields[name] = entry


def template_fields(spec: TemplateSpec) -> list[str]:
    """Campi che il template stampa, nell'ordine degli slot."""
    out: list[str] = []
    for slot in spec.slots:
        out += [f for f in slot_fields(slot) if f not in out]
    return out


def custom_field_labels(spec: TemplateSpec, labels: dict[str, str]) -> dict[str, str]:
    """Nome leggibile dei campi personalizzati: l'etichetta del template se c'e' (es. 'Lingue'), altrimenti la descrizione."""
    out = {f.key: f.description for f in spec.fields}
    for slot in spec.slots:
        if slot.kind == "label_lines":
            for ln in slot.options.get("lines", []):
                key, lk = ln.get("field"), ln.get("label_key")
                if key in out and lk and labels.get(lk):
                    out[key] = labels[lk].rstrip(": ")
    return out
