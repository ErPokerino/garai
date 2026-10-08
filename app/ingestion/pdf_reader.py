"""Lettura di PDF con PyMuPDF: testo a blocchi (rispetta le colonne), rimozione di intestazioni ripetute, fallback per scansioni."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pymupdf

LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
    "\u00ad": "",
}


def _clean(text: str) -> str:
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    return text


def _norm(line: str) -> str:
    return " ".join(line.split()).lower()


def _page_blocks(page) -> list[str]:
    """Blocchi di testo in ordine di flusso del documento (di norma colonna per colonna)."""
    blocks = page.get_text("blocks")
    out: list[str] = []
    for b in blocks:
        if b[6] != 0:  # solo blocchi di testo
            continue
        txt = _clean(b[4]).strip()
        # unisce le righe spezzate da sillabazione "competen-\nza"
        txt = re.sub(r"-\n(?=[a-z])", "", txt)
        txt = re.sub(r"[ \t]*\n[ \t]*", "\n", txt)
        if txt:
            out.append(txt)
    return out


def read_pdf(path: str | Path) -> tuple[str, bool]:
    """Ritorna (testo, probabile_scansione). I blocchi presenti nella maggioranza delle pagine
    (intestazioni/colonne laterali ripetute) vengono riportati UNA volta in testa."""
    doc = pymupdf.open(str(path))
    pages = [_page_blocks(p) for p in doc]
    n = len(pages)
    total_chars = sum(len(b) for pg in pages for b in pg)
    scanned = n > 0 and (total_chars / n) < 200

    repeated: set[str] = set()
    if n >= 3:
        counts = Counter(_norm(b) for pg in pages for b in set(pg))
        repeated = {k for k, c in counts.items() if c >= max(3, int(n * 0.6))}

    out: list[str] = []
    for pi, pg in enumerate(pages, 1):
        kept = [b for b in pg if _norm(b) not in repeated and not re.fullmatch(r"-- \d+ of \d+ --", b.strip())]
        out.append(f"[pagina {pi}]\n" + "\n".join(kept))
    header = ""
    if repeated:
        first = [b for b in (pages[0] if pages else []) if _norm(b) in repeated]
        header = "[INTESTAZIONE RIPETUTA SU OGNI PAGINA]\n" + "\n".join(first) + "\n"
    return header + "\n".join(out), scanned


def render_pages(path: str | Path, out_dir: str | Path, dpi: int = 110, max_pages: int = 8) -> list[Path]:
    """Rendering delle pagine in PNG per il fallback con modello a visione."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    paths: list[Path] = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=dpi)
        p = out_dir / f"{Path(path).stem}_p{i + 1}.png"
        pix.save(str(p))
        paths.append(p)
    return paths
