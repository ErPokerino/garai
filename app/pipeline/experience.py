"""Calcolo deterministico degli anni di esperienza (l'LLM non deve fare aritmetica sulle date)."""
from __future__ import annotations

import re
from datetime import date

from app.schemas import CVCanonical, CVExperience

UNITS = {
    "it": ("anno", "anni", "mese", "mesi"),
    "en": ("year", "years", "month", "months"),
    "es": ("año", "años", "mes", "meses"),
    "fr": ("an", "ans", "mois", "mois"),
    "de": ("Jahr", "Jahre", "Monat", "Monate"),
    "pt": ("ano", "anos", "mês", "meses"),
    "ro": ("an", "ani", "lună", "luni"),
}
PRESENT = {"it": "oggi", "en": "present", "es": "actualidad", "fr": "aujourd'hui", "de": "heute", "pt": "atualidade", "ro": "prezent"}


def parse_ym(s: str | None, end: bool = False) -> int | None:
    """'YYYY-MM' o 'YYYY' -> indice mese assoluto (anno*12+mese-1)."""
    if not s:
        return None
    m = re.match(r"^\s*(\d{4})(?:[-/](\d{1,2}))?", s)
    if not m:
        return None
    y = int(m.group(1))
    if m.group(2):
        mo = min(max(int(m.group(2)), 1), 12)
    else:
        mo = 12 if end else 1
    return y * 12 + mo - 1


def _interval(e: CVExperience, today: date) -> tuple[int, int] | None:
    start = parse_ym(e.start)
    if start is None:
        return None
    if e.is_current:
        end = today.year * 12 + today.month - 1
    elif e.end:
        end = parse_ym(e.end, end=True)
    else:
        end = start  # fine ignota: conta il solo mese di inizio
    if end is None or end < start:
        return None
    return start, end + 1  # estremo destro esclusivo (il mese di fine conta)


def total_months(cv: CVCanonical, today: date | None = None) -> int:
    today = today or date.today()
    ivs = sorted(iv for e in cv.experiences if (iv := _interval(e, today)))
    total, cur_s, cur_e = 0, None, None
    for s, e in ivs:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def format_experience(months: int, language: str) -> str | None:
    if months <= 0:
        return None
    one_y, many_y, one_m, many_m = UNITS.get(language, UNITS["en"])
    if months < 12:
        return f"{months} {one_m if months == 1 else many_m}"
    years = (months + 6) // 12  # arrotondamento "commerciale" (round() di Python arrotonda 2.5 a 2)
    return f"{years} {one_y if years == 1 else many_y}"


def end_sort_key(e: CVExperience, today: date | None = None) -> int:
    """Chiave di ordinamento per recenza (piu' alto = piu' recente)."""
    today = today or date.today()
    if e.is_current:
        return 10**6
    return parse_ym(e.end, end=True) or parse_ym(e.start) or 0
