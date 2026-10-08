"""Caricamento uniforme di documenti sorgente (bando, CV) a partire da DOCX/PDF/TXT."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .docx_reader import read_docx
from .pdf_reader import read_pdf, render_pages


@dataclass
class SourceDocument:
    filename: str
    path: Path
    text: str
    scanned: bool = False  # True se il testo e' troppo scarso: usare il fallback a visione
    page_images: list[Path] = field(default_factory=list)


def load_document(path: str | Path, work_dir: str | Path | None = None) -> SourceDocument:
    path = Path(path)
    ext = path.suffix.lower()
    scanned = False
    images: list[Path] = []
    if ext == ".docx":
        text = read_docx(path)
    elif ext == ".pdf":
        text, scanned = read_pdf(path)
        if scanned and work_dir is not None:
            images = render_pages(path, Path(work_dir) / "pages")
    elif ext in (".txt", ".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"Formato non supportato: {ext} ({path.name}). Usa DOCX, PDF o TXT.")
    return SourceDocument(filename=path.name, path=path, text=text, scanned=scanned, page_images=images)
