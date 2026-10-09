"""Interventi del bid manager in fase di controllo: dati del candidato, indicazioni, esclusione."""
import pytest

from app.pipeline.llm_schemas import Assignment
from app.pipeline.tailor import write_content
from app.schemas import BandoSpec, CVCanonical, ProfileSpec, WriterOutput
from app.service.runs import RunManager, RunState, _now
from app.template.budget import Budgets


def _manager(tmp_path) -> tuple[RunManager, str]:
    mgr = RunManager(tmp_path / "runs")
    st = RunState(
        id="r1", created_at=_now(), updated_at=_now(), status="review",
        bando=BandoSpec(language="it", title="Gara", profiles=[ProfileSpec(id="p1", name="PM")]),
        cvs=[CVCanonical(source_file="a.docx", location="Roma"), CVCanonical(source_file="b.docx")],
        cv_files=["a.docx", "b.docx"],
        assignments={f: Assignment(profile_id="p1", confidence=0.9, rationale="ok") for f in ("a.docx", "b.docx")},
    )
    mgr._runs[st.id] = st
    return mgr, st.id


def test_details_guidance_and_exclusion(tmp_path):
    mgr, rid = _manager(tmp_path)
    st = mgr.set_assignments(rid, {}, details={
        "a.docx": {"location": "  Milano ", "email": "a@x.it", "current_role": "Lead PM", "instructions": "Evidenzia SAP"},
        "b.docx": {"excluded": True},
    }, guidance="Sempre la PA")
    a = next(c for c in st.cvs if c.source_file == "a.docx")
    assert a.location == "Milano" and a.email == "a@x.it"
    assert st.candidates["a.docx"].current_role == "Lead PM" and st.candidates["a.docx"].instructions == "Evidenzia SAP"
    assert st.candidates["b.docx"].excluded and st.guidance == "Sempre la PA"
    assert mgr.included(st) == ["a.docx"]
    est = mgr.estimate(rid)
    assert len(est["per_cv"]) <= 1  # la stima conta solo i candidati inclusi
    # ricaricato dal disco: gli interventi restano
    again = RunManager(tmp_path / "runs").get(rid)
    assert again.candidates["b.docx"].excluded and again.guidance == "Sempre la PA"


def test_invalid_request_changes_nothing(tmp_path):
    mgr, rid = _manager(tmp_path)
    with pytest.raises(ValueError, match="Almeno un candidato"):
        mgr.set_assignments(rid, {}, details={"a.docx": {"excluded": True, "location": "Napoli"}, "b.docx": {"excluded": True}})
    st = mgr.get(rid)
    assert not st.candidates and next(c for c in st.cvs if c.source_file == "a.docx").location == "Roma"
    with pytest.raises(ValueError, match="sconosciuto"):
        mgr.set_assignments(rid, {}, details={"zzz.docx": {"instructions": "x"}})


def test_instructions_reach_the_writer():
    seen = {}

    class FakeLLM:
        def structured(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
            seen["user"] = user
            return WriterOutput()

    write_content(FakeLLM(), CVCanonical(source_file="a.docx"), ProfileSpec(id="p1", name="PM"),
                  BandoSpec(language="it", profiles=[]), Budgets(), "it", instructions="Metti in evidenza SAP")
    assert "INSTRUCTIONS FROM THE BID MANAGER" in seen["user"] and "Metti in evidenza SAP" in seen["user"]
