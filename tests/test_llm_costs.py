"""Layer LLM: listino prezzi, ledger dei costi, limiti di spesa, cache, client Gemini (SDK simulato)."""
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import BudgetExceeded, Usage, UsageClient
from app.llm.client import CachedClient
from app.llm.pricing import PriceBook
from app.llm.providers import GeminiClient, inline_schema
from app.llm.usage import MeteredClient, UsageLedger
from app.schemas import WriterOutput


class Out(BaseModel):
    value: str


class FakeClient(UsageClient):
    id = "gemini"

    def __init__(self):
        self.calls = 0

    def model(self, tier):
        return "gemini-3.8-flash" if tier == "strong" else "gemini-3.5-flash-lite"

    def structured_with_usage(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        self.calls += 1
        return schema(value="x"), Usage(provider="gemini", model=self.model(tier), input_tokens=1_000_000,
                                        output_tokens=100_000, thinking_tokens=40_000)


@pytest.fixture
def ledger(tmp_path):
    return UsageLedger(tmp_path / "db.sqlite", PriceBook(tmp_path / "pricing.json"))


def test_gemini_price_steps_up_in_2027():
    pb = PriceBook(None)
    now, _ = pb.cost("gemini-3.8-flash", 1_000_000, 1_000_000, on=date(2026, 10, 8))
    later, _ = pb.cost("gemini-3.8-flash", 1_000_000, 1_000_000, on=date(2027, 1, 2))
    assert now == pytest.approx(0.75 + 3.75)
    assert later == pytest.approx(1.50 + 7.50)


def test_flash_lite_and_unknown_model():
    pb = PriceBook(None)
    usd, known = pb.cost("gemini-3.5-flash-lite", 2_000_000, 0, cache_read_tokens=1_000_000)
    assert known and usd == pytest.approx(0.60 + 0.03)
    assert pb.cost("modello-inesistente", 10, 10) == (0.0, False)
    assert pb.price("gemini-3.5-flash-lite-preview-11-2026") is not None  # prefisso noto


def test_price_override(tmp_path):
    pb = PriceBook(tmp_path / "p.json")
    pb.set_override("my-model", {"provider": "custom", "tiers": [{"from": "2000-01-01", "input": 1, "output": 2}]})
    assert pb.cost("my-model", 1_000_000, 1_000_000)[0] == pytest.approx(3)
    pb.set_override("my-model", None)
    assert pb.price("my-model") is None


def test_metered_client_records_cost_and_stage(ledger):
    m = MeteredClient(FakeClient(), ledger, run_id="r1")
    m.phase = "analysis"
    m.structured(task="cv_parse:CV_DEV", system="s", user="u", schema=Out, tier="strong")
    m.structured(task="match:CV_DEV", system="s", user="u", schema=Out, tier="fast")
    tot = ledger.totals(run_id="r1")
    assert tot["calls"] == 2
    # strong: 1M in * 0.75 + 100k out * 3.75 ; fast: 1M * 0.30 + 100k * 2.50  (prezzi 2026)
    expected = PriceBook(None).cost("gemini-3.8-flash", 1_000_000, 100_000)[0] + \
        PriceBook(None).cost("gemini-3.5-flash-lite", 1_000_000, 100_000)[0]
    assert tot["cost_usd"] == pytest.approx(expected)
    stages = {r["key"] for r in ledger.group("stage", run_id="r1")}
    assert stages == {"cv_parse", "match"}
    assert ledger.calls(run_id="r1")[0]["phase"] == "analysis"


def test_run_budget_blocks_further_calls(ledger):
    inner = FakeClient()
    m = MeteredClient(inner, ledger, run_id="r2", run_budget_usd=0.5)
    m.structured(task="write:a", system="s", user="u", schema=Out)  # ~1.125$ > 0.5$
    with pytest.raises(BudgetExceeded):
        m.structured(task="write:b", system="s", user="u", schema=Out)
    assert inner.calls == 1


def test_local_cache_hit_is_free_and_counted_as_saving(ledger, tmp_path):
    inner = FakeClient()
    m = MeteredClient(CachedClient(inner, tmp_path / "cache"), ledger, run_id="r3")
    for _ in range(2):
        m.structured(task="verify:x", system="s", user="u", schema=Out, tier="fast")
    assert inner.calls == 1
    tot = ledger.totals(run_id="r3")
    assert tot["cache_hits"] == 1 and tot["saved_usd"] > 0
    assert tot["cost_usd"] == pytest.approx(tot["saved_usd"])  # pagata una volta, risparmiata la seconda


def test_inline_schema_is_self_contained():
    import json

    s = inline_schema(WriterOutput)
    text = json.dumps(s)
    assert '"$ref"' not in text and '"$defs"' not in text
    block = s["properties"]["experiences"]["items"]
    assert "title" in block["properties"]  # proprieta' chiamata "title" conservata
    assert "title" not in block  # metadato "title" dello schema rimosso
    assert block["properties"]["bullets"]["type"] == "array"


def test_gemini_client_maps_usage_and_parses(monkeypatch):
    cfg = Settings()
    cfg.api_keys = {"gemini": "test-key", "anthropic": "", "openai": ""}
    cfg.reasoning = {"strong": "low", "fast": "auto"}
    client = GeminiClient(cfg)
    seen = {}

    def fake_generate(model, contents, config):
        seen["model"], seen["config"] = model, config
        um = SimpleNamespace(prompt_token_count=1200, cached_content_token_count=200, candidates_token_count=80,
                             thoughts_token_count=300)
        return SimpleNamespace(text='{"value": "ok"}', usage_metadata=um, candidates=[])

    monkeypatch.setattr(client._c.models, "generate_content", fake_generate)
    out, u = client.structured_with_usage(task="t", system="sys", user="u", schema=Out, tier="strong")
    assert out.value == "ok"
    assert seen["model"] == "gemini-3.8-flash"
    assert seen["config"].response_json_schema["properties"]["value"]["type"] == "string"
    assert seen["config"].thinking_config.thinking_level.value == "LOW"
    assert (u.input_tokens, u.cache_read_tokens, u.output_tokens, u.thinking_tokens) == (1000, 200, 380, 300)


def test_gemini_client_retries_on_invalid_json(monkeypatch):
    cfg = Settings()
    cfg.api_keys = {"gemini": "k", "anthropic": "", "openai": ""}
    client = GeminiClient(cfg)
    answers = iter(['{"value": ', '{"value": "fixed"}'])

    def fake_generate(model, contents, config):
        um = SimpleNamespace(prompt_token_count=10, cached_content_token_count=None, candidates_token_count=5,
                             thoughts_token_count=None)
        return SimpleNamespace(text=next(answers), usage_metadata=um, candidates=[])

    monkeypatch.setattr(client._c.models, "generate_content", fake_generate)
    out, u = client.structured_with_usage(task="t", system="s", user="u", schema=Out, tier="fast")
    assert out.value == "fixed" and u.attempts == 2 and u.input_tokens == 20
