"""Nome della pratica modificabile e spesa giornaliera nel fuso orario dell'utente."""
from zoneinfo import ZoneInfo

import pytest

from app.llm.pricing import PriceBook
from app.llm.usage import UsageLedger
from app.service.runs import RunManager, RunState, _now


def test_title_can_be_renamed(tmp_path):
    mgr = RunManager(tmp_path / "runs")
    st = RunState(id="r1", created_at=_now(), updated_at=_now(), title="ANNEX B")
    mgr._runs[st.id] = st
    mgr.set_options("r1", title="  Gara   Enel 2026 ")
    assert st.title == "Gara Enel 2026" and st.title_custom
    assert st.output_file() == "Gara Enel 2026 - CV.pptx"  # senza nome file scelto segue il nome della pratica
    with pytest.raises(ValueError):
        mgr.set_options("r1", title="   ")


def _ledger(tmp_path, stamps):
    led = UsageLedger(tmp_path / "usage.db", PriceBook(tmp_path / "prices.json"))
    with led._conn() as c:
        for ts, cost in stamps:
            c.execute(
                "INSERT INTO llm_calls (ts, stage, task, provider, model, cost_usd) VALUES (?, 'write', 't', 'gemini', 'm', ?)",
                (ts, cost),
            )
    return led


def test_daily_spend_uses_the_user_time_zone(tmp_path):
    # 23:30 UTC dell'8 ottobre e' gia' il 9 ottobre a Roma (UTC+2)
    led = _ledger(tmp_path, [("2026-10-08T23:30:00+00:00", 0.10), ("2026-10-09T20:57:00+00:00", 0.20)])
    by_day, by_day_model = led.daily(tz=ZoneInfo("Europe/Rome"))
    assert [(d["key"], round(d["cost_usd"], 2)) for d in by_day] == [("2026-10-09", 0.30)]
    assert by_day_model[0]["model"] == "m" and by_day_model[0]["calls"] == 2
    utc_days, _ = led.daily()
    assert [d["key"] for d in utc_days] == ["2026-10-08", "2026-10-09"]
