"""Regole sui contenuti: competenze solo se presenti nel CV, aziende anonimizzate, nome mai inventato, nome del file."""
from pathlib import Path

import pytest

from app.ingestion.loader import SourceDocument
from app.pipeline.llm_schemas import VerifyResult
from app.pipeline.run import CVItem, Pipeline
from app.pipeline.tailor import assemble_person, company_mentions, company_names, scrub_companies
from app.schemas import BandoSpec, CVCanonical, CVExperience, ExperienceBlock, ProfileSpec, WriterOutput
from app.service.runs import RunManager, RunOptions, RunState, _now, clean_output_name
from app.template.budget import Budgets

CV = CVCanonical(
    source_file="cv.docx",
    experiences=[
        CVExperience(company="ABSTRACT SRL", client="EssilorLuxottica", role="PM", start="2022"),
        CVExperience(company="Iren S.p.A.", role="Analyst", start="2018", end="2021"),
        CVExperience(company="Freelance", role="Dev", start="2015", end="2017"),
    ],
)
PROFILE = ProfileSpec(id="p1", name="PM")


def test_company_names_strip_legal_forms_and_generic_words():
    names = company_names(CV)
    assert set(names) == {"ABSTRACT", "EssilorLuxottica", "Iren"}


def test_scrub_removes_every_company_and_tidies_text():
    w = WriterOutput(summary="PM in Abstract per EssilorLuxottica, prima in IREN.", skills=["SAP"],
                     experiences=[ExperienceBlock(title="Retail/EssilorLuxottica - Mercurio", role="PM", bullets=["Gestione per Iren"])])
    c = assemble_person(CV, PROFILE, w, "it", hide_companies=True)
    assert c.current_company is None  # niente settore dal writer: la riga resta vuota, mai il nome
    removed = scrub_companies(c, company_names(CV))
    assert set(removed) == {"ABSTRACT", "EssilorLuxottica", "Iren"}
    assert not company_mentions(c, company_names(CV))
    assert c.experiences[0].title == "Retail - Mercurio"
    assert "Abstract" not in c.summary and "Iren" not in c.summary.title()


def test_hidden_companies_use_the_sector():
    w = WriterOutput(current_company_sector="Consulenza IT")
    assert assemble_person(CV, PROFILE, w, "it", hide_companies=True).current_company == "Consulenza IT"
    assert assemble_person(CV, PROFILE, w, "it").current_company == "ABSTRACT SRL"


def test_missing_name_is_left_empty():
    c = assemble_person(CVCanonical(source_file="x.pdf"), PROFILE, WriterOutput(), "it")
    assert c.full_name == "" and c.name_is_placeholder
    assert any("lasciato vuoto" in w for w in c.warnings)


class FakeLLM:
    """Writer che aggiunge una competenza non presente nel CV; verificatore che la segnala."""

    def __init__(self):
        self.calls = []

    def model(self, tier):
        return "fake"

    def structured(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        self.calls.append(task)
        if schema is VerifyResult:
            return VerifyResult(unsupported_skills=["Kubernetes"])
        return WriterOutput(summary="Profilo.", skills=["Java", "Kubernetes", "SQL"])


def test_unsupported_skills_are_removed_and_stay_out():
    llm = FakeLLM()
    pipe = Pipeline(llm)
    item = CVItem(SourceDocument(path=Path("cv.docx"), filename="cv.docx", text="Java e SQL"), CV)
    bando = BandoSpec(language="it", profiles=[PROFILE])
    _, content, _ = pipe._write_person(item, PROFILE, None, bando, Budgets(fields_on_template=["skills"], skills_max_items=8))
    assert content.skills == ["Java", "SQL"]
    assert any("Kubernetes" in w for w in content.warnings)
    # una riscrittura successiva (es. per lo spazio) non la reintroduce
    again = pipe._assemble(CV, PROFILE, WriterOutput(skills=["Java", "kubernetes"]), "it", None, None)
    assert again.skills == ["Java"]


@pytest.mark.parametrize("raw,clean", [
    ("Offerta Enel: CV team", "Offerta Enel CV team"),
    ("  Gara/2026 \\ lotto*1.pptx ", "Gara 2026 lotto 1"),
    ("...", ""),
])
def test_clean_output_name(raw, clean):
    assert clean_output_name(raw) == clean


def test_output_file_name_and_options(tmp_path):
    mgr = RunManager(tmp_path / "runs")
    st = RunState(id="r1", created_at=_now(), updated_at=_now(), title="ANNEX B – Profili", status="done")
    mgr._runs[st.id] = st
    assert st.output_file() == "ANNEX B _ Profili - CV.pptx"
    mgr.set_options("r1", output_name="CV Enel 2026.pptx", hide_companies=True)
    assert st.output_file() == "CV Enel 2026.pptx" and st.options.hide_companies
    with pytest.raises(ValueError):
        mgr.set_options("r1", output_name="???")
    assert RunOptions().hide_companies is False
