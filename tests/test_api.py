"""API end-to-end con risposte LLM preregistrate: crea run (upload) -> analisi -> stima -> genera -> modifica -> ricostruisci.

I file di esempio (bando + CV reali) non sono versionati: senza `samples/` i test di generazione vengono saltati.
"""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings

S = Path(__file__).resolve().parents[1] / "samples"
CVS = ["CV_DEV.docx", "CV_PM.docx", "CV_SA02.pdf", "CVDEV03.docx", "CVSA01.docx", "CVSA03.docx"]
needs_samples = pytest.mark.skipif(not (S / "fixtures").exists(), reason="file di esempio non presenti (non versionati)")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "data_dir", data)
    from app.api import server
    from app.auth import AuthService
    from app.llm.client import build_client
    from app.service.runs import RunManager

    mgr = RunManager(data / "runs")

    def fixture_client(st):  # risposte preregistrate, mai il provider reale
        return build_client(fixtures_dir=S / "fixtures", use_cache=False, remote=False, run_id=st.id)

    mp.setattr(mgr, "_client", fixture_client)
    mp.setattr(server, "runs", mgr)
    mp.setattr(server, "auth", AuthService(data))
    with TestClient(server.app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "123"}).status_code == 200
        yield c
    mp.undo()


def _wait(client, run_id, statuses, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/runs/{run_id}").json()
        if r["status"] in statuses:
            return r
        assert r["status"] != "error", r.get("error")
        time.sleep(0.5)
    raise TimeoutError(run_id)


@pytest.fixture(scope="module")
def generated(client):
    if not (S / "fixtures").exists():
        pytest.skip("file di esempio non presenti (non versionati)")
    # provider "configurato" con una chiave finta: le risposte arrivano comunque solo dalle fixture
    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "provider", "gemini")
    mp.setattr(settings, "api_keys", {**settings.api_keys, "gemini": "fake-key-for-tests"})
    try:
        return _generate(client)
    finally:
        mp.undo()


def _generate(client):
    bando = next(S.glob("Annex B ITA*.docx"))
    files = [("bando", (bando.name, bando.read_bytes()))] + [("cvs", (n, (S / n).read_bytes())) for n in CVS]
    r = client.post("/api/runs", files=files, data={"visual_critic": "false"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    review = _wait(client, rid, {"review"})
    assert len(review["cvs"]) == 6 and review["bando"]["language"] == "it"
    est = client.get(f"/api/runs/{rid}/estimate").json()
    assert est["expected"] > 0
    first = next(iter(review["assignments"]))
    a = review["assignments"][first]
    r = client.put(f"/api/runs/{rid}/assignments", json={"assignments": {first: {**a}}})
    assert r.status_code == 200
    # nome inserito a mano in revisione per un CV che non lo riporta
    nameless = next(c["source_file"] for c in review["cvs"] if not c["full_name"])
    r = client.put(f"/api/runs/{rid}/assignments", json={"names": {nameless: "  Giulia   Verdi "}})
    assert next(c for c in r.json()["cvs"] if c["source_file"] == nameless)["full_name"] == "Giulia Verdi"
    client.post(f"/api/runs/{rid}/generate", json={"visual_critic": False})
    done = _wait(client, rid, {"done"})
    return rid, done


def test_create_run_requires_provider(client):
    r = client.post("/api/runs", files=[("bando", ("b.docx", b"x")), ("cvs", ("c.docx", b"x"))])
    assert r.status_code == 400 and "provider" in r.json()["detail"].lower()


def test_demo_endpoint_removed(client):
    assert client.post("/api/runs/demo").status_code in (404, 405)


def test_status_and_settings_masking(client):
    st = client.get("/api/status").json()
    assert "demo_available" not in st and st["configured"] is False
    s = client.get("/api/settings").json()
    assert set(s["keys"]) == {"anthropic", "openai", "gemini"}
    assert all("masked" in v for v in s["keys"].values())
    assert s["default_models"]["gemini"] == {"strong": "gemini-3.8-flash", "fast": "gemini-3.5-flash-lite"}


def test_settings_roundtrip_never_returns_key(client):
    r = client.put("/api/settings", json={"api_keys": {"gemini": "AIza-test-1234567890"}, "provider": "gemini",
                                          "run_budget_usd": 2.5}).json()
    assert r["keys"]["gemini"]["set"] is True
    assert "1234567890" not in str(r)
    assert r["run_budget_usd"] == 2.5 and r["resolved_provider"] == "gemini"
    r = client.put("/api/settings", json={"api_keys": {"gemini": ""}, "provider": "auto", "run_budget_usd": 0}).json()
    assert r["keys"]["gemini"]["set"] is False


def test_generation_outputs(client, generated):
    rid, done = generated
    res = done["result"]
    assert len(res["report"]["people"]) == 6
    assert all(not p["fit_issues"] for p in res["report"]["people"])
    assert all(p["slides"] for p in res["report"]["people"])
    f = client.get(f"/api/runs/{rid}/files/{res['pptx']}?download=true")
    assert f.status_code == 200 and f.content[:2] == b"PK"
    assert client.get(f"/api/runs/{rid}/files/../../settings.json").status_code == 404


def test_manual_name_is_used_and_not_flagged(client, generated):
    _, done = generated
    named = [p["content"] for p in done["result"]["report"]["people"] if p["content"]["full_name"] == "Giulia Verdi"]
    assert len(named) == 1 and named[0]["name_is_placeholder"] is False


def test_edit_and_rebuild(client, generated):
    rid, done = generated
    person = done["result"]["report"]["people"][0]["content"]
    person["summary"] = "Profilo modificato a mano."
    person["skills"] = person["skills"][:3]
    r = client.put(f"/api/runs/{rid}/people/{person['source_file']}", json=person)
    assert r.status_code == 200 and r.json()["result"]["pending_edits"] is True
    client.post(f"/api/runs/{rid}/rebuild")
    again = _wait(client, rid, {"done"})
    assert again["result"]["edited"] is True and again["result"]["pending_edits"] is False
    p0 = next(p for p in again["result"]["report"]["people"] if p["content"]["source_file"] == person["source_file"])
    assert p0["content"]["summary"] == "Profilo modificato a mano."
    assert len(p0["content"]["skills"]) == 3


def test_fixture_run_never_calls_paid_provider(client, generated):
    """Con le risposte preregistrate nessuna chiamata finisce nel registro dei costi, anche con una chiave configurata."""
    rid, _ = generated
    calls = client.get(f"/api/costs/calls?run_id={rid}").json()
    assert calls == []


def test_runs_list_and_costs(client, generated):
    rid, _ = generated
    runs = client.get("/api/runs").json()
    assert any(r["id"] == rid and "demo" not in r for r in runs)
    summary = client.get("/api/costs/summary?days=30").json()
    assert {"totals", "by_day", "by_model", "by_stage", "by_run"} <= set(summary)
    assert client.get("/api/pricing").json()[0]["current"] is not None
