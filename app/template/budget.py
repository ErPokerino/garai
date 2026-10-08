"""Budget di testo per slot, calcolati dalla geometria reale del template e dai font."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from pptx import Presentation
from pptx.util import Emu

from app.schemas import TemplateSpec

from .measure import CM_TO_PT, TextMeter
from .spec import template_path
from .xmlutil import shape_by_id

INSET_CM = 0.1  # 36000 EMU di margine nelle colonne esperienza
BULLET_INDENT_CM = 0.5  # marL 179388 EMU
PILL_INSET_CM = 0.3  # 108000 EMU per lato


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
    columns: list[ColumnGeom] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        d = asdict(self)
        d.pop("columns", None)
        return d


def _emu_cm(v: int) -> float:
    return Emu(v).cm


def compute_budgets(spec: TemplateSpec, meter: TextMeter, max_experiences: int = 6) -> Budgets:
    prs = Presentation(str(template_path(spec)))
    b = Budgets()

    # --- Sintesi (free_text) ---
    s = spec.slot("summary")
    pt = s.font_pt or 12
    lines = meter.max_lines(s.box.h, pt)
    cpl = meter.chars_per_line(s.box.w, pt)
    b.summary_max_lines = lines
    b.summary_max_chars = int(lines * cpl * 0.92)  # margine per word-wrap

    # --- Formazione (bullets) ---
    bg = spec.slot("background")
    pt = bg.font_pt or 11
    space_after = bg.options.get("space_after_pt", 0)
    per_line_h = meter.line_height_pt(pt)
    avail_pt = bg.box.h * CM_TO_PT
    # ogni voce occupa almeno una riga + spazio dopo; stimiamo con voci di 1-2 righe
    b.background_line_chars = meter.chars_per_line(bg.box.w, pt, indent_cm=BULLET_INDENT_CM)
    b.background_max_lines = int(avail_pt / (per_line_h + space_after * 0.5))

    # --- Competenze (pills) ---
    sk = spec.slot("skills")
    pt = sk.font_pt or 12
    cols = sk.options["columns"]
    rows = sk.options["max_rows"]
    b.skills_max_items = len(cols) * rows
    min_w = min(c["w"] for c in cols)
    b.skills_max_chars = int(meter.chars_per_line(min_w, pt, indent_cm=2 * PILL_INSET_CM) * 0.95)

    # --- Ruolo/azienda ---
    rc = spec.slot("role_company")
    b.role_company_max_chars = int(rc.options.get("max_chars", 44))

    # --- Esperienze (colonne) ---
    ex = spec.slot("experiences")
    slide_idx = next(r.index for r in spec.slides if r.key == ex.slide)
    slide = prs.slides[slide_idx]
    pt = ex.font_pt or 10
    limit = spec.bottom_limit_cm
    for sid in ex.shape_ids:
        sh = shape_by_id(slide, sid)
        top = _emu_cm(sh.top)
        width = ex.options.get("column_width_cm") or _emu_cm(sh.width)
        b.columns.append(ColumnGeom(sid, _emu_cm(sh.left), top, width, usable_h=limit - top - 2 * INSET_CM))
    bpc = ex.options.get("blocks_per_column", 2)
    b.exp_blocks_per_column = bpc
    b.exp_max_blocks = min(max_experiences, len(b.columns) * bpc)
    b.exp_bullets_per_block = ex.options.get("bullets_per_block", 4)

    min_text_w = min(c.w for c in b.columns) - 2 * INSET_CM
    col_lines = min(meter.max_lines(c.usable_h, pt) for c in b.columns)
    block_lines = (col_lines - (bpc - 1)) // bpc
    title_lines, role_lines, blank_lines = 1, 2, 1
    b.exp_bullet_lines_total = max(2, block_lines - title_lines - role_lines - blank_lines)
    b.exp_title_chars = int(meter.chars_per_line(min_text_w, pt, bold=True) * title_lines * 0.95)
    b.exp_role_chars = int(meter.chars_per_line(min_text_w, pt) * role_lines * 0.9)
    bullet_cpl = meter.chars_per_line(min_text_w, pt, indent_cm=BULLET_INDENT_CM)
    b.exp_bullet_chars = int(bullet_cpl * 2 * 0.92)
    return b
