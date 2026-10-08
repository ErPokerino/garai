"""Riempimento delle slide clonate dal template secondo il Template Spec.

Principio: non si genera mai una slide da zero. Si clonano le slide del template, si sostituisce
il testo conservando i run/pPr originali e si clonano i blocchi ripetibili (pillole, paragrafi,
colonne di esperienza). Le shape da controllare sul rendering reale vengono marcate nel nome
(`slot:<id>:<persona>[:extra]|chk=<regola>`), cosi' l'overflow checker sa cosa verificare.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from lxml import etree
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.presentation import Presentation
from pptx.slide import Slide
from pptx.util import Cm, Emu, Pt

from app.schemas import ExperienceBlock, FitIssue, PersonContent, Slot, TemplateSpec

from .measure import CM_TO_PT, TextMeter
from .spec import template_path
from .xmlutil import (
    A_NS,
    append_run,
    clear_paragraph_content,
    first_rpr,
    make_run,
    max_shape_id,
    paragraph_from_proto,
    paragraphs,
    qa,
    remove_shape,
    set_cnv_id,
    set_shape_name,
    shape_by_id,
    style_rpr,
    txbody,
)

LANG_TAGS = {
    "it": "it-IT", "en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE",
    "pt": "pt-PT", "ro": "ro-RO",
}
FONT = "Work Sans"
INSET_CM = 0.1
BULLET_INDENT_CM = 0.5
PILL_INSET_CM = 0.3


def lang_tag(lang: str) -> str:
    return LANG_TAGS.get(lang, lang)


def shorten(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "\u2026"


@dataclass
class Protos:
    """Elementi del template usati come prototipo (catturati prima della clonazione)."""

    title_para: etree._Element
    role_para: etree._Element
    blank_para: etree._Element
    bullet_para: etree._Element
    pill: etree._Element


def extract_protos(prs: Presentation, spec: TemplateSpec) -> Protos:
    ex = spec.slot("experiences")
    ex_slide = prs.slides[next(r.index for r in spec.slides if r.key == ex.slide)]
    col = shape_by_id(ex_slide, ex.options["proto_column"])
    ps = paragraphs(txbody(col))
    bullet = next(p for p in ps if p.find(f"{{{A_NS}}}pPr") is not None and p.find(f"{{{A_NS}}}pPr").find(qa("buChar")) is not None)
    sk = spec.slot("skills")
    sk_slide = prs.slides[next(r.index for r in spec.slides if r.key == sk.slide)]
    pill = shape_by_id(sk_slide, sk.shape_ids[0])
    return Protos(
        title_para=copy.deepcopy(ps[0]),
        role_para=copy.deepcopy(ps[1]),
        blank_para=copy.deepcopy(ps[2]),
        bullet_para=copy.deepcopy(bullet),
        pill=copy.deepcopy(pill._element),
    )


@dataclass
class FillContext:
    spec: TemplateSpec
    labels: dict[str, str]
    lang: str
    protos: Protos
    meter: TextMeter
    content: PersonContent
    person_idx: int
    slide_no: int = 0  # numero (1-based) della slide nel deck finale
    exp_chunk: list[ExperienceBlock] | None = None
    issues: list[FitIssue] = field(default_factory=list)

    @property
    def tag(self) -> str:
        return lang_tag(self.lang)

    def warn(self, slot: str, detail: str, severity: str = "warning") -> None:
        self.issues.append(FitIssue(slide=self.slide_no, slot=slot, detail=detail, severity=severity))


# ----------------------------------------------------------------------------- helpers

def _name(slot_id: str, ctx: FillContext, extra: str = "", chk: str | None = None) -> str:
    n = f"slot:{slot_id}:{ctx.person_idx}" + (f":{extra}" if extra else "")
    return n + (f"|chk={chk}" if chk else "")


def _set_single_text(shape, text: str, ctx: FillContext) -> None:
    tb = txbody(shape)
    p0 = paragraphs(tb)[0]
    rpr = first_rpr(p0)
    if rpr is None:
        end = p0.find(qa("endParaRPr"))
        rpr = copy.deepcopy(end) if end is not None else None
        if rpr is not None:
            rpr.tag = qa("rPr")
    clear_paragraph_content(p0)
    append_run(p0, make_run(text, style_rpr(rpr, lang=ctx.tag)))
    end = p0.find(qa("endParaRPr"))
    if end is not None and "err" in end.attrib:
        del end.attrib["err"]


def _remove_ids(slide: Slide, ids: list[int]) -> None:
    for sid in ids:
        sh = shape_by_id(slide, sid)
        if sh is not None:
            remove_shape(sh)


def _get(ctx: FillContext, field_name: str | None):
    if not field_name:
        return None
    return getattr(ctx.content, field_name, None)


# ----------------------------------------------------------------------------- kinds

def fill_static_label(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    sh = shape_by_id(slide, slot.shape_ids[0])
    _set_single_text(sh, ctx.labels[slot.options["label_key"]], ctx)
    if "width_cm" in slot.options:
        sh.width = Cm(slot.options["width_cm"])


def fill_text(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    sh = shape_by_id(slide, slot.shape_ids[0])
    value = _get(ctx, slot.field)
    if not value:
        remove_shape(sh)
        return
    _set_single_text(sh, str(value), ctx)
    set_shape_name(sh, _name(slot.id, ctx, chk="lines:1"))


def fill_label_lines(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    sh = shape_by_id(slide, slot.shape_ids[0])
    tb = txbody(sh)
    ps = paragraphs(tb)
    proto = copy.deepcopy(ps[0])
    base_rpr = first_rpr(ps[0])
    sep = slot.options.get("separator", " ")
    value_bold = slot.options.get("value_bold")
    max_chars = slot.options.get("max_chars")

    new_ps: list[etree._Element] = []
    for line in slot.options["lines"]:
        value = _get(ctx, line.get("field"))
        if not value:
            continue
        value = str(value)
        if max_chars and len(value) > max_chars:
            ctx.warn(slot.id, f"valore troncato a {max_chars} caratteri")
            value = shorten(value, max_chars)
        label_key = line.get("label_key")
        p = copy.deepcopy(proto)
        clear_paragraph_content(p)
        if label_key:
            append_run(p, make_run(ctx.labels[label_key] + sep, style_rpr(base_rpr, lang=ctx.tag)))
            append_run(p, make_run(value, style_rpr(base_rpr, lang=ctx.tag, bold=bool(value_bold))))
        else:
            append_run(p, make_run(value, style_rpr(base_rpr, lang=ctx.tag, bold=True if value_bold else None)))
        end = p.find(qa("endParaRPr"))
        if end is not None and "err" in end.attrib:
            del end.attrib["err"]
        new_ps.append(p)

    if not new_ps:
        remove_shape(sh)
        _remove_ids(slide, slot.remove_shape_ids_if_empty)
        return
    for p in ps:
        tb.remove(p)
    for p in new_ps:
        tb.append(p)
    set_shape_name(sh, _name(slot.id, ctx, chk=f"lines:{len(new_ps)}"))


def _add_textbox(slide: Slide, slot: Slot, ctx: FillContext, extra_name: str = "") -> object:
    b = slot.box
    tb = slide.shapes.add_textbox(Cm(b.x), Cm(b.y), Cm(b.w), Cm(b.h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    set_shape_name(tb, _name(slot.id, ctx, extra_name, chk="h"))
    return tb


def fill_free_text(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    text = _get(ctx, slot.field)
    if not text:
        return
    tb = _add_textbox(slide, slot, ctx)
    body = txbody(tb)
    for p in paragraphs(body):
        body.remove(p)
    pt = slot.font_pt or 12
    space_after = slot.options.get("space_after_pt", 0)
    for chunk in str(text).split("\n"):
        p = etree.SubElement(body, qa("p"))
        if space_after:
            ppr = etree.SubElement(p, qa("pPr"))
            spc = etree.SubElement(ppr, qa("spcAft"))
            etree.SubElement(spc, qa("spcPts")).set("val", str(int(space_after * 100)))
        append_run(p, make_run(chunk, style_rpr(None, size_pt=pt, lang=ctx.tag, font=FONT)))


def fill_bullets(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    items = _get(ctx, slot.field) or []
    if not items:
        label = slot.options.get("label_shape_id")  # senza voci non ha senso lasciare il titolo della sezione
        if label is not None:
            _remove_ids(slide, [label])
        return
    tb = _add_textbox(slide, slot, ctx)
    body = txbody(tb)
    for p in paragraphs(body):
        body.remove(p)
    pt = slot.font_pt or 11
    space_after = slot.options.get("space_after_pt", 0)
    for item in items:
        p = paragraph_from_proto(ctx.protos.bullet_para, [(item, False)], size_pt=pt, lang=ctx.tag)
        ppr = p.find(qa("pPr"))
        if ppr is not None:
            # spaziatura coerente con lo spec; rimuove spcAft/spcBef del prototipo
            for tag in ("spcBef", "spcAft"):
                el = ppr.find(qa(tag))
                if el is not None:
                    ppr.remove(el)
            if space_after:
                spc = etree.Element(qa("spcAft"))
                etree.SubElement(spc, qa("spcPts")).set("val", str(int(space_after * 100)))
                # l'ordine schema: lnSpc, spcBef, spcAft, bu*
                ln = ppr.find(qa("lnSpc"))
                if ln is not None:
                    ln.addnext(spc)
                else:
                    ppr.insert(0, spc)
        body.append(p)


def fill_pills(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    _remove_ids(slide, slot.remove_shape_ids)
    skills = list(_get(ctx, slot.field) or [])
    cols = slot.options["columns"]
    rows = slot.options["max_rows"]
    cap = len(cols) * rows
    pt = slot.font_pt or 12
    if len(skills) > cap:
        ctx.warn(slot.id, f"{len(skills) - cap} competenze oltre la capacita' ({cap}) omesse")
        skills = skills[:cap]
    next_id = max_shape_id(slide) + 1
    tree = slide.shapes._spTree
    placed = 0
    for i, skill in enumerate(skills):
        col = cols[placed % len(cols)]
        row = placed // len(cols)
        text_w = ctx.meter.width_pt(skill, pt)
        avail_w = (col["w"] - 2 * PILL_INSET_CM) * CM_TO_PT
        if text_w > avail_w:
            ctx.warn(slot.id, f"competenza '{skill}' troppo lunga per la pillola, omessa")
            continue
        el = copy.deepcopy(ctx.protos.pill)
        set_cnv_id(el, next_id, _name(slot.id, ctx, str(i), chk="lines:1"))
        next_id += 1
        xfrm = el.find(f"{{http://schemas.openxmlformats.org/presentationml/2006/main}}spPr").find(qa("xfrm"))
        off, ext = xfrm.find(qa("off")), xfrm.find(qa("ext"))
        off.set("x", str(int(Cm(col["x"]))))
        off.set("y", str(int(Cm(slot.options["first_row_y"] + row * slot.options["row_pitch"]))))
        ext.set("cx", str(int(Cm(col["w"]))))
        ext.set("cy", str(int(Cm(slot.options["pill_h"]))))
        body = txbody(el)
        p0 = paragraphs(body)[0]
        rpr = first_rpr(p0)
        clear_paragraph_content(p0)
        append_run(p0, make_run(skill, style_rpr(rpr, size_pt=pt, lang=ctx.tag)))
        tree.append(el)
        placed += 1


def fill_experience_columns(slide: Slide, slot: Slot, ctx: FillContext) -> None:
    blocks = ctx.exp_chunk if ctx.exp_chunk is not None else ctx.content.experiences
    pt = slot.font_pt or 10
    limit = ctx.spec.bottom_limit_cm
    n_cols = len(slot.shape_ids)
    _remove_ids(slide, slot.remove_shape_ids)
    per_col: list[list[ExperienceBlock]] = [[] for _ in range(n_cols)]
    for i, blk in enumerate(blocks):
        per_col[i % n_cols].append(blk)
    pr = ctx.protos
    role_label = ctx.labels[slot.options["role_label_key"]]

    for ci, sid in enumerate(slot.shape_ids):
        sh = shape_by_id(slide, sid)
        col_blocks = per_col[ci]
        if not col_blocks:
            remove_shape(sh)
            continue
        top_cm = Emu(sh.top).cm
        sh.height = Cm(limit - top_cm)
        if slot.options.get("column_width_cm"):
            sh.width = Cm(slot.options["column_width_cm"])
        tb = txbody(sh)
        for p in paragraphs(tb):
            tb.remove(p)
        for bi, blk in enumerate(col_blocks):
            if bi > 0:
                tb.append(paragraph_from_proto(pr.blank_para, [(" ", None)], size_pt=pt, lang=ctx.tag))
            tb.append(paragraph_from_proto(pr.title_para, [(blk.title, True)], size_pt=pt, lang=ctx.tag))
            role_text = blk.role + (f" ({blk.period})" if blk.period else "")
            tb.append(
                paragraph_from_proto(
                    pr.role_para, [(role_label + " ", False), (role_text, False)], size_pt=pt, lang=ctx.tag
                )
            )
            tb.append(paragraph_from_proto(pr.blank_para, [(" ", None)], size_pt=pt, lang=ctx.tag))
            for bullet in blk.bullets:
                tb.append(paragraph_from_proto(pr.bullet_para, [(bullet, False)], size_pt=pt, lang=ctx.tag))
        set_shape_name(sh, _name(slot.id, ctx, f"c{ci}", chk="h"))


KIND_HANDLERS = {
    "static_label": fill_static_label,
    "text": fill_text,
    "label_lines": fill_label_lines,
    "free_text": fill_free_text,
    "bullets": fill_bullets,
    "pills": fill_pills,
    "experience_columns": fill_experience_columns,
}


def fill_slide(slide: Slide, slide_key: str, ctx: FillContext) -> None:
    for slot in ctx.spec.slots_for(slide_key):
        _remove_ids(slide, [] if slot.kind in ("pills", "experience_columns") else slot.remove_shape_ids)
        KIND_HANDLERS[slot.kind](slide, slot, ctx)
