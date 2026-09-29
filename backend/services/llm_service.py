"""Groq LLM access via the official `groq` Python SDK (OpenAI-compatible chat completions)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

import groq
from groq import AsyncGroq

from config import get_settings

log = logging.getLogger("opsmind.llm")


class LLMError(Exception):
    def __init__(self, message: str, code: str = "llm_unavailable", status: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


_client: AsyncGroq | None = None


def is_configured() -> bool:
    return bool(get_settings().groq_api_key)


def model_name() -> str:
    return get_settings().groq_model


def _get_client() -> AsyncGroq:
    global _client
    s = get_settings()
    if not s.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set. Add it to .env to enable the OpsMind agent.", code="llm_not_configured", status=503)
    if _client is None:
        # Retries are handled here explicitly (max_llm_retries), so disable SDK retries.
        _client = AsyncGroq(api_key=s.groq_api_key, timeout=s.groq_timeout_seconds, max_retries=0)
    return _client


def agent_model_name() -> str:
    return get_settings().groq_agent_model or model_name()


def _extra_params(effort: str, model: str | None = None) -> dict[str, Any]:
    if (model or model_name()).startswith("openai/gpt-oss"):
        return {"reasoning_effort": effort}
    return {}


OnWait = Callable[[float, str], Awaitable[None]] | None
OnSwitch = Callable[[str, str], Awaitable[None]] | None
MAX_RATE_LIMIT_WAIT = 30.0


def _retry_after(e: Exception) -> float | None:
    """Seconds Groq asks us to wait (retry-after header or 'try again in 13.4s' in the message)."""
    resp = getattr(e, "response", None)
    if resp is not None:
        ra = resp.headers.get("retry-after")
        if ra:
            try:
                return float(ra)
            except ValueError:
                pass
    m = re.search(r"try again in ([0-9.]+)(ms|s)", str(e))
    if m:
        v = float(m.group(1))
        return v / 1000 if m.group(2) == "ms" else v
    return None


class RateLimited(LLMError):
    def __init__(self, wait: float | None):
        super().__init__("Groq rate limit reached. Wait a moment and retry.", code="llm_rate_limited", status=503)
        self.wait = wait


async def _create(on_wait: OnWait = None, model: str | None = None, fail_fast_on_rate_limit: bool = False, **kwargs):
    client = _get_client()
    model = model or model_name()
    attempts = get_settings().max_llm_retries
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = await client.chat.completions.create(model=model, **kwargs)
            u = getattr(resp, "usage", None)
            if u is not None:
                cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", None)
                log.info("Groq usage [%s]: prompt=%s cached=%s completion=%s", model, u.prompt_tokens, cached, u.completion_tokens)
            return resp
        except groq.AuthenticationError as e:
            log.error("Groq auth failed: %s", e)
            raise LLMError("Groq rejected the API key. Check GROQ_API_KEY.", code="llm_auth")
        except groq.NotFoundError as e:
            log.error("Groq model not found: %s", e)
            raise LLMError(f"Groq model '{model}' is not available. Check GROQ_MODEL / GROQ_AGENT_MODEL.", code="llm_model")
        except groq.BadRequestError as e:
            # gpt-oss occasionally emits a malformed tool call -> Groq returns 400 tool_use_failed. Retry.
            body = getattr(e, "body", None) or {}
            code = (body.get("error") or {}).get("code") if isinstance(body, dict) else None
            log.warning("Groq bad request (attempt %d/%d, code=%s): %s", attempt, attempts, code, str(e)[:300])
            if code not in ("tool_use_failed", "json_validate_failed", "output_parse_failed"):
                raise LLMError("The LLM request was rejected by Groq.", code="llm_bad_request")
            last = e
        except groq.RateLimitError as e:
            wait = _retry_after(e)
            log.warning("Groq rate limited [%s] (attempt %d/%d), retry-after=%s", model, attempt, attempts, wait)
            last = e
            if fail_fast_on_rate_limit:
                raise RateLimited(wait)
            if attempt < attempts and wait is not None and wait <= MAX_RATE_LIMIT_WAIT:
                if on_wait:
                    await on_wait(wait, "Groq free-tier token-per-minute limit")
                await asyncio.sleep(wait + 0.5)
                continue
        except (groq.APITimeoutError, groq.APIConnectionError, groq.InternalServerError) as e:
            log.warning("Groq transient error (attempt %d/%d): %r", attempt, attempts, e)
            last = e
        except groq.APIStatusError as e:
            log.warning("Groq status error (attempt %d/%d): %s", attempt, attempts, e.status_code)
            last = e
        if attempt < attempts:
            await asyncio.sleep(0.8 * attempt)
    if isinstance(last, groq.RateLimitError):
        raise LLMError("Groq rate limit reached. Wait a moment and retry.", code="llm_rate_limited", status=503)
    if isinstance(last, (groq.APITimeoutError, groq.APIConnectionError)):
        raise LLMError("Groq is unreachable or timed out.", code="llm_unavailable", status=503)
    raise LLMError(f"Groq LLM call failed after {attempts} attempts.", code="llm_failed")


def agent_model_chain() -> list[str]:
    s = get_settings()
    chain = [agent_model_name()] + [m.strip() for m in s.groq_agent_fallback_models.split(",") if m.strip()]
    return list(dict.fromkeys(chain))


async def chat_with_tools(messages: list[dict[str, Any]], tools: list[dict[str, Any]], on_wait: OnWait = None,
                          on_switch: OnSwitch = None):
    """One agent step. Returns (assistant message, model used).

    Each Groq model has its own tokens-per-minute bucket, so when the agent model is rate
    limited we fail over to the next model in GROQ_AGENT_FALLBACK_MODELS instead of sleeping.
    Only the last model in the chain waits for the retry-after window.
    max_completion_tokens is kept small: Groq counts it against the TPM budget up front.
    """
    chain = agent_model_chain()
    for i, model in enumerate(chain):
        last = i == len(chain) - 1
        try:
            resp = await _create(
                on_wait=on_wait, model=model, fail_fast_on_rate_limit=not last, messages=messages, tools=tools,
                tool_choice="auto", temperature=0.2, max_completion_tokens=400, **_extra_params("low", model),
            )
        except RateLimited:
            if on_switch:
                await on_switch(model, chain[i + 1])
            continue
        if not resp.choices:
            raise LLMError("Groq returned an empty response.", code="llm_malformed")
        return resp.choices[0].message, model
    raise LLMError("All Groq agent models are rate limited.", code="llm_rate_limited", status=503)


def structured_model_chain() -> list[str]:
    fallbacks = [m.strip() for m in get_settings().groq_structured_fallback_models.split(",") if m.strip()]
    return list(dict.fromkeys([model_name()] + fallbacks))


async def structured(messages: list[dict[str, Any]], schema_name: str, schema: dict[str, Any], effort: str = "low",
                     max_tokens: int = 2400, on_wait: OnWait = None, on_switch: OnSwitch = None,
                     models: list[str] | None = None, used: dict[str, str] | None = None) -> dict[str, Any]:
    """Structured output with strict JSON schema (tools cannot be combined with this on Groq).

    Model chain: GROQ_MODEL first, failing over to GROQ_STRUCTURED_FALLBACK_MODELS when a model's
    TPM bucket is exhausted. Per model, falls back to json_object mode if strict mode fails.
    """
    chain = models or structured_model_chain()
    for i, model in enumerate(chain):
        last = i == len(chain) - 1
        try:
            out = await _structured_one(model, messages, schema_name, schema, effort, max_tokens, on_wait, fail_fast=not last)
            if used is not None:
                used["model"] = model
            return out
        except RateLimited:
            if on_switch:
                await on_switch(model, chain[i + 1])
    raise LLMError("All Groq models are rate limited.", code="llm_rate_limited", status=503)


async def _structured_one(model, messages, schema_name, schema, effort, max_tokens, on_wait, fail_fast) -> dict[str, Any]:
    common = dict(on_wait=on_wait, model=model, fail_fast_on_rate_limit=fail_fast, max_completion_tokens=max_tokens,
                  **_extra_params(effort, model))
    try:
        resp = await _create(
            messages=messages, temperature=0.2,
            response_format={"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            **common,
        )
        return _parse_json(resp.choices[0].message.content)
    except RateLimited:
        raise
    except (LLMError, ValueError) as e:
        if isinstance(e, LLMError) and e.code in ("llm_auth", "llm_not_configured", "llm_model"):
            raise
        log.warning("Strict structured output failed on %s (%s); retrying in json_object mode", model, e)
    resp = await _create(
        messages=messages + [{"role": "user", "content": "Return ONLY a JSON object matching this JSON schema:\n" + json.dumps(schema)}],
        temperature=0.1, response_format={"type": "json_object"}, **common,
    )
    try:
        return _parse_json(resp.choices[0].message.content)
    except ValueError as e:
        raise LLMError("The LLM returned malformed JSON.", code="llm_malformed") from e


def _parse_json(content: str | None) -> dict[str, Any]:
    if not content:
        raise ValueError("empty content")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


async def ping() -> dict[str, Any]:
    client = _get_client()
    try:
        models = await asyncio.wait_for(client.models.list(), timeout=8)
    except groq.AuthenticationError:
        raise LLMError("Groq rejected the API key.", code="llm_auth")
    except Exception as e:
        log.warning("Groq ping failed: %r", e)
        raise LLMError("Groq is unreachable.", code="llm_unavailable", status=503)
    ids = {m.id for m in models.data}
    return {"connected": True, "model": model_name(), "agent_model": agent_model_name(),
            "model_available": model_name() in ids and agent_model_name() in ids}
