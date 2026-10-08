"""Duplicazione di slide dentro una presentazione python-pptx (con relazioni a immagini/svg)."""
from __future__ import annotations

import copy

from pptx.presentation import Presentation
from pptx.slide import Slide

from .xmlutil import P_NS, R_NS


def clone_slide(prs: Presentation, src: Slide) -> Slide:
    new = prs.slides.add_slide(src.slide_layout)
    # elimina i placeholder creati da add_slide: copiamo tutto dalla sorgente
    for shp in list(new.shapes):
        shp._element.getparent().remove(shp._element)

    src_tree = src.shapes._spTree
    new_tree = new.shapes._spTree
    for child in src_tree.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in ("nvGrpSpPr", "grpSpPr"):
            continue
        new_tree.append(copy.deepcopy(child))

    # sfondo / clrMapOvr della slide sorgente
    src_bg = src._element.cSld.find(f"{{{P_NS}}}bg")
    if src_bg is not None:
        new._element.cSld.insert(0, copy.deepcopy(src_bg))

    _remap_relationships(src, new, new_tree)
    return new


def _remap_relationships(src: Slide, new: Slide, tree) -> None:
    rid_map: dict[str, str] = {}
    for el in tree.iter():
        for attr, val in list(el.attrib.items()):
            if not attr.startswith(f"{{{R_NS}}}"):
                continue
            if val not in rid_map:
                rel = src.part.rels[val]
                if rel.is_external:
                    rid_map[val] = new.part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
                else:
                    rid_map[val] = new.part.relate_to(rel.target_part, rel.reltype)
            el.set(attr, rid_map[val])


def delete_slides(prs: Presentation, indices: list[int]) -> None:
    sld_id_lst = prs.slides._sldIdLst
    ids = list(sld_id_lst)
    for i in sorted(indices, reverse=True):
        sld_id = ids[i]
        prs.part.drop_rel(sld_id.rId)
        sld_id_lst.remove(sld_id)
