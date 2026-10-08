"""Client dei provider remoti (Anthropic, OpenAI, Google Gemini) con output strutturato Pydantic e conteggio dei token.

Ogni client espone `structured_with_usage(...) -> (oggetto validato, Usage)`. Strategia comune:
1. output strutturato nativo del provider (schema JSON imposto lato server);
2. se il provider rifiuta lo schema, ripiego su "JSON nel prompt" con validazione Pydantic e fino a 3 tentativi;
3. se rifiuta il livello di ragionamento richiesto, riprova con il default del modello.
"""
from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.config import Settings

from .base import UsageClient, Usage, img_b64, json_from_text

JSON_ONLY = "\n\nRispondi ESCLUSIVAMENTE con un oggetto JSON valido conforme a questo JSON Schema:\n"


def _now_ms() -> float:
    return time.perf_counter() * 1000


def inline_schema(schema: type[BaseModel]) -> dict:
    """JSON Schema autocontenuto (senza $defs/$ref, senza title/default): il sottoinsieme piu' portabile tra provider."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                return walk(copy.deepcopy(defs[name]))
            out = {}
            for k, v in node.items():
                if k in ("title", "default"):
                    continue
                if k == "properties":  # i nomi delle proprieta' (anche "title") vanno conservati
                    out[k] = {name: walk(sub) for name, sub in v.items()}
                else:
                    out[k] = walk(v)
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(raw)


def _retryable(fn, *, is_retryable, attempts: int = 4):
    """Backoff esponenziale con jitter per errori transitori (429/5xx)."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1 or not is_retryable(e):
                raise
            time.sleep(min(2 ** i + random.random(), 20))


# ============================================================================ Anthropic
EFFORT = {"minimal": "low", "low": "low", "medium": "medium", "high": "high"}


class AnthropicClient(UsageClient):
    id = "anthropic"

    def __init__(self, cfg: Settings):
        import anthropic

        self._anthropic = anthropic
        self._c = anthropic.Anthropic(api_key=cfg.api_key("anthropic") or None, max_retries=3)
        self._models = {t: cfg.model_for("anthropic", t) for t in ("strong", "fast")}
        self._reasoning = dict(cfg.reasoning)
        self._json_mode = False  # diventa True se il modello non supporta gli structured output

    def model(self, tier: str) -> str:
        return self._models[tier]

    @staticmethod
    def _usage(resp, u: Usage) -> None:
        x = resp.usage
        u.add(
            Usage(
                input_tokens=x.input_tokens or 0,
                output_tokens=x.output_tokens or 0,
                cache_read_tokens=getattr(x, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(x, "cache_creation_input_tokens", 0) or 0,
            )
        )

    def structured_with_usage(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        a = self._anthropic
        model = self._models[tier]
        content: list[dict] = []
        for p in images or []:
            mt, b64 = img_b64(p)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}})
        content.append({"type": "text", "text": user})
        # i modelli attuali ragionano prima di rispondere: i token di ragionamento rientrano in max_tokens
        base = dict(model=model, max_tokens=max(max_tokens, 16000), messages=[{"role": "user", "content": content}])
        effort = EFFORT.get(self._reasoning.get(tier, "auto"))
        if effort:
            base["output_config"] = {"effort": effort}

        u = Usage(provider=self.id, model=model, attempts=0)
        t0 = _now_ms()
        last_err: Exception | None = None
        feedback: str | None = None
        for _ in range(4):
            u.attempts += 1
            kw = dict(base)
            try:
                if not self._json_mode:
                    resp = self._c.messages.parse(system=system, output_format=schema, **kw)
                    self._usage(resp, u)
                    if resp.stop_reason == "refusal":
                        raise RuntimeError(f"[{task}] richiesta rifiutata dal modello")
                    if resp.parsed_output is not None:
                        u.latency_ms = int(_now_ms() - t0)
                        return resp.parsed_output, u
                    last_err = RuntimeError(f"nessun output strutturato (stop_reason={resp.stop_reason})")
                    continue
                msgs = list(kw.pop("messages"))
                if feedback:
                    msgs = msgs + [{"role": "user", "content": feedback}]
                resp = self._c.messages.create(
                    system=system + JSON_ONLY + json.dumps(schema.model_json_schema(), ensure_ascii=False),
                    messages=msgs, **kw,
                )
                self._usage(resp, u)
                text = "".join(b.text for b in resp.content if b.type == "text")
                try:
                    out = schema.model_validate(json_from_text(text))
                    u.latency_ms = int(_now_ms() - t0)
                    return out, u
                except (ValidationError, json.JSONDecodeError) as e:
                    last_err = e
                    feedback = f"Il JSON precedente non era valido: {e}. Riemetti solo il JSON corretto."
            except a.BadRequestError as e:
                msg = str(e).lower()
                if "output_config" in base and ("effort" in msg or "output_config" in msg):
                    base.pop("output_config")  # modello senza supporto all'effort: usa il default
                    last_err = e
                    continue
                if not self._json_mode and ("output_format" in msg or "schema" in msg or "structured" in msg):
                    self._json_mode = True  # structured output non supportato: ripiego su JSON nel prompt
                    last_err = e
                    continue
                raise
            except ValidationError as e:
                last_err = e
        raise RuntimeError(f"[{task}] output strutturato non ottenuto: {last_err}")


# ============================================================================ OpenAI
class OpenAIClient(UsageClient):
    id = "openai"

    def __init__(self, cfg: Settings):
        import openai

        self._openai = openai
        self._c = openai.OpenAI(api_key=cfg.api_key("openai") or None, max_retries=3)
        self._models = {t: cfg.model_for("openai", t) for t in ("strong", "fast")}
        self._reasoning = dict(cfg.reasoning)

    def model(self, tier: str) -> str:
        return self._models[tier]

    def structured_with_usage(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        model = self._models[tier]
        parts: list[dict] = [{"type": "text", "text": user}]
        for p in images or []:
            mt, b64 = img_b64(p)
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
        sys_msg = system + JSON_ONLY + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": parts}]
        extra: dict = {}
        lvl = self._reasoning.get(tier, "auto")
        if lvl != "auto":
            extra["reasoning_effort"] = lvl
        u = Usage(provider=self.id, model=model, attempts=0)
        t0 = _now_ms()
        last_err: Exception | None = None
        for _ in range(4):
            u.attempts += 1
            try:
                resp = self._c.chat.completions.create(
                    model=model, messages=messages, max_completion_tokens=max(max_tokens, 16000),
                    response_format={"type": "json_object"}, **extra,
                )
            except self._openai.BadRequestError as e:
                if extra and "reasoning" in str(e).lower():
                    extra = {}
                    last_err = e
                    continue
                raise
            x = resp.usage
            if x is not None:
                cached = getattr(getattr(x, "prompt_tokens_details", None), "cached_tokens", 0) or 0
                reasoning = getattr(getattr(x, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
                u.add(Usage(input_tokens=(x.prompt_tokens or 0) - cached, output_tokens=x.completion_tokens or 0,
                            thinking_tokens=reasoning, cache_read_tokens=cached))
            text = resp.choices[0].message.content or ""
            try:
                out = schema.model_validate(json_from_text(text))
                u.latency_ms = int(_now_ms() - t0)
                return out, u
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"JSON non valido: {e}. Correggi e riemetti solo il JSON."},
                ]
        raise RuntimeError(f"[{task}] output strutturato non ottenuto: {last_err}")


# ============================================================================ Google Gemini
class GeminiClient(UsageClient):
    """Gemini via SDK `google-genai` (es. gemini-3.8-flash, gemini-3.5-flash-lite).

    Usa `response_json_schema` (schema reso autocontenuto) e `thinking_level` se impostato. I token di ragionamento
    (`thoughts_token_count`) sono fatturati come output e vengono conteggiati come tali.
    """

    id = "gemini"

    def __init__(self, cfg: Settings):
        from google import genai
        from google.genai import errors, types

        self._types = types
        self._errors = errors
        key = cfg.api_key("gemini")
        if not key:
            raise RuntimeError("GEMINI_API_KEY mancante")
        self._c = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=600_000))
        self._models = {t: cfg.model_for("gemini", t) for t in ("strong", "fast")}
        self._reasoning = dict(cfg.reasoning)
        self._schema_mode = True  # False se il modello rifiuta response_json_schema

    def model(self, tier: str) -> str:
        return self._models[tier]

    def _is_retryable(self, e: Exception) -> bool:
        code = getattr(e, "code", None)
        return isinstance(e, self._errors.ServerError) or code in (408, 429, 500, 502, 503, 504)

    def structured_with_usage(self, *, task, system, user, schema, tier="strong", images=None, max_tokens=8000):
        types = self._types
        model = self._models[tier]
        parts = [types.Part.from_bytes(data=Path(p).read_bytes(), mime_type=img_b64(p)[0]) for p in images or []]
        parts.append(types.Part.from_text(text=user))
        level = self._reasoning.get(tier, "auto")
        thinking = level if level != "auto" else None

        u = Usage(provider=self.id, model=model, attempts=0)
        t0 = _now_ms()
        last_err: Exception | None = None
        contents = [types.Content(role="user", parts=parts)]
        for _ in range(4):
            u.attempts += 1
            cfg_kw: dict = dict(
                system_instruction=system if self._schema_mode else system + JSON_ONLY + json.dumps(inline_schema(schema)),
                response_mime_type="application/json",
                max_output_tokens=max(max_tokens, 16000),
            )
            if self._schema_mode:
                cfg_kw["response_json_schema"] = inline_schema(schema)
            if thinking:
                cfg_kw["thinking_config"] = types.ThinkingConfig(thinking_level=thinking.upper())
            try:
                resp = _retryable(
                    lambda: self._c.models.generate_content(
                        model=model, contents=contents, config=types.GenerateContentConfig(**cfg_kw)
                    ),
                    is_retryable=self._is_retryable,
                )
            except self._errors.ClientError as e:
                msg = str(e).lower()
                if thinking and "think" in msg:
                    thinking = None  # livello non supportato dal modello: default
                    last_err = e
                    continue
                if self._schema_mode and getattr(e, "code", None) == 400 and "schema" in msg:
                    self._schema_mode = False
                    last_err = e
                    continue
                raise
            um = resp.usage_metadata
            if um is not None:
                prompt = um.prompt_token_count or 0
                cached = um.cached_content_token_count or 0
                thoughts = um.thoughts_token_count or 0
                u.add(Usage(input_tokens=prompt - cached, output_tokens=(um.candidates_token_count or 0) + thoughts,
                            thinking_tokens=thoughts, cache_read_tokens=cached))
            text = resp.text or ""
            try:
                out = schema.model_validate(json_from_text(text))
                u.latency_ms = int(_now_ms() - t0)
                return out, u
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                last_err = e
                finish = resp.candidates[0].finish_reason if resp.candidates else None
                contents = [
                    types.Content(role="user", parts=parts),
                    types.Content(role="model", parts=[types.Part.from_text(text=text[:20000] or "{}")]),
                    types.Content(role="user", parts=[types.Part.from_text(
                        text=f"Output non valido ({e}; finish_reason={finish}). Riemetti solo il JSON completo e corretto."
                    )]),
                ]
        raise RuntimeError(f"[{task}] output strutturato non ottenuto: {last_err}")


def ping(provider: str, cfg: Settings) -> dict:
    """Chiamata minima per verificare chiave e modello (usata da 'Test connessione' nella UI)."""

    class Pong(BaseModel):
        ok: bool

    cls = {"anthropic": AnthropicClient, "openai": OpenAIClient, "gemini": GeminiClient}[provider]
    client = cls(cfg)
    out = {}
    for tier in ("fast", "strong"):
        obj, u = client.structured_with_usage(
            task="ping", system="Reply with ok=true.", user="ping", schema=Pong, tier=tier, max_tokens=200
        )
        out[tier] = {"model": client.model(tier), "ok": bool(obj.ok), "latency_ms": u.latency_ms,
                     "input_tokens": u.input_tokens, "output_tokens": u.output_tokens}
    return out
