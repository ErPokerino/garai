"""Nome segnaposto quando il CV non riporta il nome (regola di progetto: va inventato, coerente con la lingua)."""
from __future__ import annotations

import hashlib

NAMES = {
    "it": (
        ["Marco", "Luca", "Giulia", "Francesca", "Alessandro", "Chiara", "Matteo", "Elena", "Davide", "Sara", "Andrea", "Valentina"],
        ["Rossi", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco", "Conti", "De Luca", "Mancini", "Costa", "Fontana"],
    ),
    "en": (
        ["James", "Emily", "Daniel", "Sophie", "Michael", "Laura", "Thomas", "Hannah", "Oliver", "Grace"],
        ["Walker", "Hughes", "Turner", "Bennett", "Carter", "Morgan", "Reed", "Foster", "Hayes", "Parker"],
    ),
    "es": (
        ["Javier", "Lucia", "Carlos", "Marta", "Pablo", "Elena", "Diego", "Laura"],
        ["Garcia", "Martinez", "Lopez", "Sanchez", "Fernandez", "Romero", "Navarro", "Torres"],
    ),
    "fr": (
        ["Julien", "Camille", "Nicolas", "Claire", "Antoine", "Marie", "Thomas", "Elodie"],
        ["Martin", "Bernard", "Dubois", "Moreau", "Laurent", "Lefebvre", "Girard", "Roux"],
    ),
    "de": (
        ["Lukas", "Anna", "Jonas", "Lena", "Felix", "Julia", "Paul", "Sophie"],
        ["Schneider", "Fischer", "Weber", "Wagner", "Becker", "Hoffmann", "Koch", "Richter"],
    ),
    "pt": (
        ["Joao", "Ana", "Pedro", "Marta", "Tiago", "Ines", "Rui", "Sofia"],
        ["Silva", "Santos", "Ferreira", "Pereira", "Costa", "Oliveira", "Rodrigues", "Martins"],
    ),
    "ro": (
        ["Andrei", "Elena", "Mihai", "Ioana", "Radu", "Maria", "Stefan", "Ana"],
        ["Popescu", "Ionescu", "Dumitru", "Stan", "Constantin", "Marin", "Radu", "Dinu"],
    ),
}


def invent_name(language: str, seed: str) -> str:
    """Nome plausibile e stabile (stesso seed -> stesso nome), nella lingua richiesta."""
    firsts, lasts = NAMES.get(language, NAMES["en"])
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return f"{firsts[h % len(firsts)]} {lasts[(h // len(firsts)) % len(lasts)]}"
