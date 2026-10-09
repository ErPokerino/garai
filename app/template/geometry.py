"""Geometria degli slot: area utile di ogni slot calcolata dal template reale, senza presupposti sul layout.

Uno slot puo' avere un'area esplicita (`box`, in cm) oppure riferirsi a una shape del template. Per gli slot che
contengono testo di lunghezza variabile (elenchi, paragrafi) l'area si estende verso il basso fino al primo elemento
del template che si trova sotto (stessa colonna) oppure fino al limite inferiore della slide (piede di pagina).
"""
from __future__ import annotations

from pptx.presentation import Presentation
from pptx.slide import Slide
from pptx.util import Emu

from app.schemas import Box, Slot, TemplateSpec

from .xmlutil import iter_shapes, shape_by_id

GROWING_KINDS = ("free_text", "bullets", "experience_columns")
GAP_CM = 0.15  # distanza minima dall'elemento sottostante


def cm(v: int | None) -> float:
    return Emu(v or 0).cm


def slide_size_cm(prs: Presentation) -> tuple[float, float]:
    return cm(prs.slide_width), cm(prs.slide_height)


def slide_of(prs: Presentation, spec: TemplateSpec, slot: Slot) -> Slide:
    idx = next(r.index for r in spec.slides if r.key == slot.slide)
    return prs.slides[idx]


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def free_bottom(slide: Slide, x: float, w: float, top: float, limit: float, exclude: set[int]) -> float:
    """Ordinata (cm) del primo elemento sotto `top` che si sovrappone in orizzontale all'intervallo [x, x+w]."""
    bottom = limit
    for sh in iter_shapes(slide.shapes):
        if sh.shape_id in exclude or sh.top is None or sh.left is None:
            continue
        sx, sy, sw = cm(sh.left), cm(sh.top), cm(sh.width)
        if sy <= top + 0.05:
            continue
        # le linee sottili sotto un titolo non bloccano; contano i blocchi che occupano almeno un quarto della larghezza
        if _overlap(x, x + w, sx, sx + sw) < 0.25 * min(w, max(sw, 0.01)):
            continue
        bottom = min(bottom, sy - GAP_CM)
    return bottom


def slot_area(prs: Presentation, spec: TemplateSpec, slot: Slot) -> Box | None:
    """Area (cm) in cui lo slot scrive. None se lo slot non ha ne' box ne' shape valida."""
    W, H = slide_size_cm(prs)
    limit = min(spec.bottom_limit_cm, H)
    if slot.box is not None:
        b = slot.box
        x, y = max(0.0, b.x), max(0.0, b.y)
        w = max(0.5, min(b.w, W - x))
        h = max(0.3, min(b.h, limit - y))
        return Box(x=x, y=y, w=w, h=h)
    if not slot.shape_ids:
        return None
    slide = slide_of(prs, spec, slot)
    sh = shape_by_id(slide, slot.shape_ids[0])
    if sh is None or sh.left is None:
        return None
    x, y, w, h = cm(sh.left), cm(sh.top), cm(sh.width), cm(sh.height)
    if slot.kind in GROWING_KINDS:
        h = max(h, free_bottom(slide, x, w, y, limit, exclude=set(slot.shape_ids) | set(slot.remove_shape_ids)) - y)
    return Box(x=x, y=y, w=w, h=max(0.3, h))


def auto_bottom_limit(prs: Presentation, slide: Slide) -> float:
    """Limite inferiore della zona scrivibile: sopra gli elementi di piede (layout/master) nella fascia bassa."""
    W, H = slide_size_cm(prs)
    tops = []
    for part in (slide.slide_layout, slide.slide_layout.slide_master):
        for sh in iter_shapes(part.shapes):
            if sh.top is None:
                continue
            y = cm(sh.top)
            if y > 0.8 * H and cm(sh.width) > 0.5:
                tops.append(y)
    return round(min(tops) - GAP_CM, 2) if tops else round(H - 0.8, 2)
