"""Stima del costo della fase di generazione, prima di avviarla.

Si basa su: dimensione reale dei CV analizzati e dei profili assegnati, numero atteso di chiamate per CV
(scrittura + revisioni, verifica di fedelta', critico visivo opzionale) e listino del modello configurato.
I token di ragionamento non sono prevedibili con precisione: la stima riporta un intervallo minimo-massimo.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import Settings
from app.llm import prompts
from app.llm.client import get_ledger, get_prices

if TYPE_CHECKING:  # pragma: no cover
    from .runs import RunState

CHARS_PER_TOKEN = 3.5
IMAGE_TOKENS = 1500  # slide 1600px: ordine di grandezza comune ai provider

# stage -> (livello, chiamate min, chiamate max, token output, token ragionamento min, token ragionamento max)
PLAN = {
    "write": ("strong", 1.0, 3.0, 2200, 300, 4000),
    "verify": ("fast", 1.0, 2.0, 400, 100, 1500),
}


def _tok(chars: int) -> int:
    return int(chars / CHARS_PER_TOKEN)


def estimate_generation(st: "RunState", visual_critic: bool, cfg: Settings) -> dict:
    ledger = get_ledger(cfg)
    spent = ledger.totals(run_id=st.id)
    base = {"currency": "USD", "spent_so_far": spent["cost_usd"], "calls_so_far": spent["calls"]}
    provider = cfg.resolved_provider()
    if provider == "none":
        return {**base, "min": 0.0, "max": 0.0, "expected": 0.0, "per_cv": [], "models": {},
                "notes": ["Nessun provider configurato."]}
    prices = get_prices(cfg)
    models = {t: cfg.model_for(provider, t) for t in ("strong", "fast")}
    unknown = [m for m in set(models.values()) if prices.price(m) is None]

    def cost(tier: str, tin: int, tout: int) -> float:
        return prices.cost(models[tier], tin, tout)[0]

    per_cv, tot_min, tot_max, tot_exp = [], 0.0, 0.0, 0.0
    for cv in st.cvs:
        a = st.assignments.get(cv.source_file)
        prof = st.bando.get(a.profile_id) if (a and st.bando) else None
        cv_chars = len(cv.model_dump_json(exclude_none=True))
        prof_chars = len(prof.model_dump_json(exclude_none=True)) if prof else 3000
        write_in = _tok(cv_chars + prof_chars + len(prompts.WRITER_SYSTEM) + 1500)
        verify_in = _tok(cv_chars + 3000 + len(prompts.VERIFY_SYSTEM))
        lo = hi = 0.0
        for stage, tin in (("write", write_in), ("verify", verify_in)):
            tier, cmin, cmax, out, th_min, th_max = PLAN[stage]
            lo += cmin * cost(tier, tin, out + th_min)
            # revisioni: includono anche l'output precedente nel prompt
            hi += cmax * cost(tier, tin + out, out + th_max)
        if visual_critic:
            crit_in = IMAGE_TOKENS * 4 + 400
            lo += cost("strong", crit_in, 300)
            hi += cost("strong", crit_in, 300 + 2000)
        exp = lo + (hi - lo) * 0.35
        per_cv.append({"file": cv.source_file, "min": round(lo, 5), "max": round(hi, 5), "expected": round(exp, 5)})
        tot_min, tot_max, tot_exp = tot_min + lo, tot_max + hi, tot_exp + exp

    notes = [
        "Stima basata sulla dimensione reale dei CV e dei profili; i token di ragionamento possono variare.",
        "Le chiamate già presenti in cache locale non vengono addebitate.",
    ]
    if unknown:
        notes.append(f"Prezzo non noto per: {', '.join(unknown)} (aggiungilo in Costi → Listino).")
    remaining = None
    if cfg.run_budget_usd > 0:
        remaining = max(cfg.run_budget_usd - spent["cost_usd"], 0.0)
        if tot_max > remaining:
            notes.append(f"Attenzione: lo scenario massimo supera il limite residuo del run (${remaining:.2f}).")
    return {**base, "min": round(tot_min, 5), "max": round(tot_max, 5), "expected": round(tot_exp, 5),
            "per_cv": per_cv, "models": models, "provider": provider, "run_budget_remaining": remaining,
            "notes": notes}
