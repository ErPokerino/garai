"""Rilevamento euristico della lingua (it/en/es/fr/de/pt/ro) tramite stopword, senza dipendenze esterne."""
from __future__ import annotations

import re

STOPWORDS = {
    "it": "il lo la i gli le un una di del della dei delle da in con su per tra fra e ed o che non come sono è al alla nel nella anche più nei degli dalla svolte esperienza progetto".split(),
    "en": "the of and to in a is that for with as on by are be this from or an at which have it their experience project".split(),
    "es": "el la los las de del y en un una que con para por se su al como es más experiencia proyecto".split(),
    "fr": "le la les des du de et en un une que pour par dans avec sur au aux est sont son expérience projet".split(),
    "de": "der die das und in den von zu mit für auf ist im dem nicht ein eine erfahrung projekt".split(),
    "pt": "o a os as de do da em um uma que com para por se seu ao como é mais experiência projeto".split(),
    "ro": "și în de la cu pe care este un o pentru din sau mai experiență proiect".split(),
}


def detect_language(text: str, default: str = "it") -> str:
    words = re.findall(r"[a-zàâäçéèêëîïôöùûüÿñãõăîșț]+", text.lower())
    if not words:
        return default
    sample = words[:6000]
    scores = {}
    for lang, sw in STOPWORDS.items():
        sws = set(sw)
        scores[lang] = sum(1 for w in sample if w in sws)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else default
