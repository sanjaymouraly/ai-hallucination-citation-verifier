from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import config
from app.security.url_fetch import UnsafeURLError, pinned_transport_for_public_url

from .base import ProviderConfig, ProviderError

DEFAULTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "lm_studio": "http://127.0.0.1:1234/v1",
}

# Keyless local runtimes whose default context window is small enough that hidden
# reasoning can crowd out the JSON answer.
LOCAL_PROVIDERS = {"ollama", "lm_studio"}


@dataclass(frozen=True)
class ProviderReply:
    text: str
    model: str
    prompt_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens


def _base_url(cfg: ProviderConfig) -> str:
    if cfg.provider == "custom" and not cfg.base_url:
        raise ProviderError("A base URL is required for the custom provider.")
    base = (cfg.base_url or DEFAULTS.get(cfg.provider) or "").rstrip("/")
    if not base:
        raise ProviderError("Provider base URL is not configured.")
    if cfg.provider != "anthropic" and not re.search(r"/v\d+$", base):
        base += "/v1"
    return base


def _headers(cfg: ProviderConfig) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if cfg.provider == "anthropic":
        if not cfg.api_key:
            raise ProviderError("Anthropic API key is required. Configure it in Settings or the environment.")
        headers.update({"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"})
    elif cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    elif cfg.provider in {"openai", "openrouter"}:
        raise ProviderError(f"{cfg.provider.title()} API key is required. Configure it in Settings or the environment.")
    if cfg.provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/verity-evidence-checker"
        headers["X-Title"] = "Verity Evidence Checker"
    return headers


def _safe_response_error(response: httpx.Response, provider: str) -> ProviderError:
    if response.status_code in (401, 403):
        return ProviderError(f"{provider.title()} rejected authentication (HTTP {response.status_code}). Check the key and account access.")
    if response.status_code == 429:
        return ProviderError(f"{provider.title()} rate limit reached (HTTP 429). Retry later or reduce request volume.")
    if response.status_code == 404:
        return ProviderError(f"The {provider.title()} endpoint or model was not found (HTTP 404). Check the base URL and model.")
    return ProviderError(f"{provider.title()} request failed (HTTP {response.status_code}). Provider response details were withheld.")


def _request(cfg: ProviderConfig, method: str, url: str, **kwargs: Any) -> httpx.Response:
    headers = {**_headers(cfg), **kwargs.pop("headers", {})}
    attempts = cfg.retries + 1
    for attempt in range(attempts):
        try:
            transport = None
            if cfg.provider not in {"ollama", "lm_studio"}:
                try:
                    transport = pinned_transport_for_public_url(url)
                except UnsafeURLError as exc:
                    # A single-user administrator may deliberately point a custom
                    # OpenAI-compatible endpoint at localhost. In multi-user mode,
                    # only public HTTPS custom endpoints are accepted and pinned.
                    if cfg.provider != "custom" or config.api_tokens:
                        raise ProviderError("The configured provider URL must resolve to a public address on a standard HTTP(S) port.") from exc
            with httpx.Client(timeout=cfg.timeout_seconds, follow_redirects=False, trust_env=False, transport=transport) as client:
                response = client.request(method, url, headers=headers, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(min(0.25 * (2**attempt), 1.0))
                continue
            return response
        except httpx.TimeoutException as exc:
            if attempt < attempts - 1:
                time.sleep(min(0.25 * (2**attempt), 1.0))
                continue
            raise ProviderError(f"{cfg.provider.title()} request timed out after {cfg.timeout_seconds} seconds.") from exc
        except httpx.RequestError as exc:
            if attempt < attempts - 1:
                time.sleep(min(0.25 * (2**attempt), 1.0))
                continue
            raise ProviderError(f"Could not reach the configured {cfg.provider.title()} endpoint. Check the URL and network.") from exc
    raise ProviderError(f"{cfg.provider.title()} request failed after retries.")


def _model_list(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("data", [])
    result: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                result.append(row["id"])
    return list(dict.fromkeys(result))


def _suggest_model(models: list[str], provider: str) -> str | None:
    if not models:
        return None
    # Select only an identifier returned by this provider. Prefer common chat-capable
    # names when present; model listings are not a guarantee of endpoint capability.
    hints = ("gpt-4o", "gpt-4.1", "gpt-4", "claude", "gemini", "gemma", "qwen", "llama", "instruct", "chat")
    for hint in hints:
        for model in models:
            if hint in model.lower():
                return model
    return models[0]


def test_provider(cfg: ProviderConfig) -> dict[str, Any]:
    if cfg.provider == "local":
        return {"ok": True, "provider": "local", "message": "Local deterministic analysis is ready; no network call or paid API is used.", "models": [], "suggested_model": None}
    url = _base_url(cfg) + "/models"
    response = _request(cfg, "GET", url)
    if response.status_code >= 400:
        raise _safe_response_error(response, cfg.provider)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("Provider returned an unreadable model-list response.") from exc
    models = _model_list(payload)
    suggested = cfg.model or _suggest_model(models, cfg.provider)
    if not models and not cfg.model:
        raise ProviderError("The endpoint responded, but did not list models. Enter a model identifier provided by your service.")
    message = "Connection succeeded."
    if not cfg.model and suggested:
        message += " A model identifier was discovered from the provider response; verify it supports chat completions."
    return {"ok": True, "provider": cfg.provider, "message": message, "models": models[:200], "suggested_model": suggested}


_THINK_OPEN = "<" + "think" + ">"
_THINK_CLOSE = "</" + "think" + ">"


def _strip_think_tags(text: str) -> str:
    """Remove `…` reasoning-model think blocks from the model's final answer."""
    lowered = text.lower()
    while _THINK_OPEN in lowered and _THINK_CLOSE in lowered:
        start = lowered.index(_THINK_OPEN)
        end = lowered.index(_THINK_CLOSE, start + len(_THINK_OPEN))
        text = text[:start] + text[end + len(_THINK_CLOSE):]
        lowered = text.lower()
    return text.strip()


def _extract_openai(payload: dict[str, Any], cfg: ProviderConfig) -> ProviderReply:
    try:
        choice = payload["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Provider returned an empty or malformed chat response.") from exc
    content = message.get("content")
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    finish_reason = choice.get("finish_reason")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        # Reasoning models (qwen3, deepseek-r1, …) can spend the whole output
        # budget on internal reasoning and return an empty final answer.
        if reasoning.strip() and finish_reason in {"length", "max_tokens"}:
            raise ProviderError("The model used its output budget on internal reasoning and returned no final answer. Increase 'Max output tokens' or choose a non-reasoning model.")
        raise ProviderError("Provider returned an empty chat response.")
    cleaned = _strip_think_tags(content)
    if not cleaned:
        raise ProviderError("Provider returned an empty chat response.")
    usage = payload.get("usage", {})
    return ProviderReply(cleaned, str(payload.get("model") or cfg.model or "unknown"), int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0))


def chat(cfg: ProviderConfig, system_prompt: str, user_prompt: str) -> ProviderReply:
    if cfg.provider == "local":
        raise ProviderError("The local deterministic provider does not send chat-completion requests.")
    if not cfg.model:
        raise ProviderError("Choose or discover a model in Provider Settings before enabling AI-assisted review.")
    if cfg.provider == "anthropic":
        url = _base_url(cfg) + "/messages"
        body = {"model": cfg.model, "max_tokens": cfg.max_output_tokens, "temperature": cfg.temperature, "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]}
        response = _request(cfg, "POST", url, json=body)
        if response.status_code >= 400:
            raise _safe_response_error(response, cfg.provider)
        try:
            payload = response.json()
            pieces = payload.get("content", [])
            text = "".join(str(piece.get("text", "")) for piece in pieces if isinstance(piece, dict) and piece.get("type") == "text")
            usage = payload.get("usage", {})
        except (ValueError, AttributeError) as exc:
            raise ProviderError("Anthropic returned an unreadable response.") from exc
        if not text.strip():
            raise ProviderError("Anthropic returned an empty response.")
        return ProviderReply(text.strip(), str(payload.get("model") or cfg.model), int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0))
    url = _base_url(cfg) + "/chat/completions"
    body = {"model": cfg.model, "temperature": cfg.temperature, "max_tokens": cfg.max_output_tokens, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    if cfg.provider in LOCAL_PROVIDERS:
        # Local reasoning models (qwen3, deepseek-r1, …) otherwise spend the whole
        # (often small) context window on hidden reasoning and truncate the JSON
        # answer. Ollama and LM Studio accept reasoning_effort "none"; other
        # promptable backends ignore an unrecognised field rather than failing.
        body["reasoning_effort"] = "none"
    response = _request(cfg, "POST", url, json=body)
    if response.status_code >= 400:
        raise _safe_response_error(response, cfg.provider)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("Provider returned an unreadable chat response.") from exc
    return _extract_openai(payload, cfg)


def _first_balanced_object(text: str) -> str | None:
    """Return the first brace-balanced `{...}` region, ignoring braces inside strings.

    Providers sometimes wrap the JSON object in prose or append an extra `}`; a
    string-aware scan recovers the real object where a greedy regex would not.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        start = text.find("{", start + 1)
    return None


def parse_json_reply(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.IGNORECASE)
    cleaned = _strip_think_tags(cleaned)
    candidates = [cleaned]
    balanced = _first_balanced_object(cleaned)
    if balanced:
        candidates.append(balanced)
    # Some providers prepend prose before the JSON object; prefer a balanced object
    # so a stray sentence or trailing brace does not discard a valid reply.
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    if cleaned.count("{") > cleaned.count("}"):
        raise ProviderError("The model's JSON reply was cut off by the output-token limit. Increase 'Max output tokens' or choose a non-reasoning model; local assessment was retained.")
    raise ProviderError("Provider response did not contain valid JSON; local assessment was retained.")
