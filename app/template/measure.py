"""Misura del testo con i font reali (Pillow) per stimare righe e caratteri disponibili.

La stima serve a (1) dare al writer LLM budget realistici e (2) fare un pre-controllo veloce.
La verifica finale dell'overflow avviene sul rendering reale (PowerPoint COM / LibreOffice).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from app.config import ROOT

CM_TO_PT = 72.0 / 2.54
SCALE = 20  # il font viene caricato a pt*SCALE px e le misure riportate in pt
SAFETY = 0.97  # margine: la stima usa il 97% della larghezza disponibile


class TextMeter:
    def __init__(self, regular: str | Path, bold: str | Path, line_factor: float = 1.17):
        self.regular = self._resolve(regular)
        self.bold = self._resolve(bold)
        self.line_factor = line_factor

    @staticmethod
    def _resolve(p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else ROOT / p

    @lru_cache(maxsize=64)
    def _font(self, pt: float, bold: bool) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.bold if bold else self.regular), size=max(1, int(round(pt * SCALE))))

    def width_pt(self, text: str, pt: float, bold: bool = False) -> float:
        if not text:
            return 0.0
        return self._font(pt, bold).getlength(text) / SCALE

    def line_height_pt(self, pt: float) -> float:
        return pt * self.line_factor

    def line_height_cm(self, pt: float) -> float:
        return self.line_height_pt(pt) / CM_TO_PT

    def avg_char_width_pt(self, pt: float, bold: bool = False) -> float:
        sample = "Sviluppo di applicazioni web e integrazione servizi cloud per il cliente"
        return self.width_pt(sample, pt, bold) / len(sample)

    def wrap(self, text: str, width_pt: float, pt: float, bold: bool = False) -> list[str]:
        """Word-wrap greedy; ritorna le righe risultanti."""
        width_pt = width_pt * SAFETY
        lines: list[str] = []
        for para in text.split("\n"):
            words = para.split(" ")
            cur = ""
            for w in words:
                trial = w if not cur else cur + " " + w
                if self.width_pt(trial, pt, bold) <= width_pt or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines

    def n_lines(self, text: str, width_cm: float, pt: float, bold: bool = False, indent_cm: float = 0.0) -> int:
        return len(self.wrap(text, (width_cm - indent_cm) * CM_TO_PT, pt, bold))

    def chars_per_line(self, width_cm: float, pt: float, bold: bool = False, indent_cm: float = 0.0) -> int:
        return int((width_cm - indent_cm) * CM_TO_PT * SAFETY / self.avg_char_width_pt(pt, bold))

    def max_lines(self, height_cm: float, pt: float) -> int:
        return int(height_cm / self.line_height_cm(pt))
