"""Font del template: famiglia prevalente e file da usare per la stima delle misure del testo.

La stima (usata quando PowerPoint non c'e', es. su Cloud Run) deve misurare con lo stesso font del template.
Su Linux `fc-match` risolve anche gli equivalenti metrici (Calibri -> Carlito, Arial -> Liberation Sans);
altrove si cercano i file nelle cartelle dei font di sistema e in assets/fonts.
"""
from __future__ import annotations

import collections
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont
from pptx.presentation import Presentation
from pptx.slide import Slide

from app.config import ROOT

from .xmlutil import A_NS, iter_shapes, paragraphs, qa, txbody

# equivalenti metrici liberi dei font Microsoft piu' comuni
METRIC_ALIASES = {
    "calibri": "carlito", "cambria": "caladea", "arial": "liberation sans", "helvetica": "liberation sans",
    "times new roman": "liberation serif", "courier new": "liberation mono",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def theme_fonts(prs: Presentation) -> tuple[str | None, str | None]:
    """(major, minor) latin del tema della presentazione."""
    master = prs.slide_masters[0]
    for rel in master.part.rels.values():
        if rel.reltype.endswith("/theme"):
            xml = rel.target_part.blob.decode("utf-8", "ignore")
            major = re.search(r"<a:majorFont>\s*<a:latin typeface=\"([^\"]+)\"", xml)
            minor = re.search(r"<a:minorFont>\s*<a:latin typeface=\"([^\"]+)\"", xml)
            return (major.group(1) if major else None, minor.group(1) if minor else None)
    return None, None


def dominant_font(prs: Presentation, slides: list[Slide]) -> str | None:
    """Famiglia usata per la maggior parte del testo delle slide (pesata sulla lunghezza del testo)."""
    major, minor = theme_fonts(prs)
    counts: collections.Counter[str] = collections.Counter()
    for slide in slides:
        for sh in iter_shapes(slide.shapes):
            if not sh.has_text_frame:
                continue
            for p in paragraphs(txbody(sh)):
                for r in p.findall(qa("r")):
                    text = (r.findtext(qa("t")) or "").strip()
                    if not text:
                        continue
                    latin = r.find(f"{qa('rPr')}/{qa('latin')}")
                    face = latin.get("typeface") if latin is not None else "+mn-lt"
                    face = {"+mn-lt": minor, "+mj-lt": major}.get(face, face)
                    if face:
                        counts[face] += len(text)
    if counts:
        return counts.most_common(1)[0][0]
    return minor


def _font_dirs() -> list[Path]:
    dirs = [ROOT / "assets" / "fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    windir = os.environ.get("WINDIR")
    if windir:
        dirs.append(Path(windir) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return [d for d in dirs if d.exists()]


@lru_cache(maxsize=1)
def _font_index() -> dict[str, dict[str, str]]:
    """famiglia normalizzata -> {stile normalizzato: file}. Letto una volta per processo."""
    index: dict[str, dict[str, str]] = {}
    for d in _font_dirs():
        for f in d.rglob("*"):
            if f.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                family, style = ImageFont.truetype(str(f), 10).getname()
            except Exception:  # noqa: BLE001 - file non leggibile
                continue
            index.setdefault(_norm(family or ""), {}).setdefault(_norm(style or "regular"), str(f))
    return index


def _fc_match(pattern: str) -> str | None:
    if not shutil.which("fc-match"):
        return None
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    f = out.stdout.strip()
    return f if f and Path(f).suffix.lower() in (".ttf", ".otf") else None


@lru_cache(maxsize=32)
def resolve_font_files(family: str) -> tuple[str, str] | None:
    """(regolare, grassetto) per la famiglia, o il suo equivalente metrico. None se non trovata."""
    names = [family, METRIC_ALIASES.get(family.lower(), "")]
    for name in filter(None, names):
        styles = _font_index().get(_norm(name))
        if styles:
            regular = styles.get("regular") or styles.get("book") or next(iter(styles.values()))
            bold = styles.get("bold") or styles.get("semibold") or regular
            return regular, bold
    regular, bold = _fc_match(family), _fc_match(f"{family}:bold")
    if regular:
        return regular, bold or regular
    return None


_ = A_NS
