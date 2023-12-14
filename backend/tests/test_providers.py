from __future__ import annotations

import httpx
import pytest

from app.core.config import config
from app.providers import adapters
from app.providers.adapters import chat, parse_json_reply
from app.providers.adapters import test_provider as check_provider
from app.providers.base import ProviderConfig, ProviderError


def test_local_provider_connection_test_never_uses_network():
    result = check_provider(ProviderConfig(provider="local"))
    assert result["ok"] is True
    assert "no network" in result["message"].lower()


def test_remote_provider_requires_credentials():
    with pytest.raises(ProviderError, match="API key is required"):
        check_provider(ProviderConfig(provider="openai"))


def test_cloud_provider_rejects_private_custom_endpoint_before_connecting():
    cfg = ProviderConfig(provider="openai", base_url="http://127.0.0.1/v1", api_key="test-secret")
    with pytest.raises(ProviderError, match="public address"):
        adapters._request(cfg, "GET", "http://127.0.0.1/v1/models")


def test_multitenant_custom_provider_cannot_target_private_addresses():
    previous = config.api_tokens_raw
    object.__setattr__(config, "api_tokens_raw", "reviewer=" + "r" * 40)
    try:
        cfg = ProviderConfig(provider="custom", base_url="http://127.0.0.1:8000/v1", api_key="test-secret")
        with pytest.raises(ProviderError, match="public address"):
            adapters._request(cfg, "GET", "http://127.0.0.1:8000/v1/models")
    finally:
        object.__setattr__(config, "api_tokens_raw", previous)


def test_model_discovery_uses_only_provider_returned_ids(monkeypatch):
    response = httpx.Response(200, json={"data": [{"id": "other-model"}, {"id": "gpt-4o-mini"}]})
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    result = check_provider(ProviderConfig(provider="openai", api_key="test-secret"))
    assert result["suggested_model"] == "gpt-4o-mini"
    assert result["models"] == ["other-model", "gpt-4o-mini"]


def test_provider_error_does_not_echo_response_body(monkeypatch):
    response = httpx.Response(401, text="secret-token-value must not be returned")
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    with pytest.raises(ProviderError) as error:
        check_provider(ProviderConfig(provider="openai", api_key="hidden"))
    assert "HTTP 401" in str(error.value)
    assert "secret-token-value" not in str(error.value)
    assert "hidden" not in str(error.value)


def test_chat_sends_structured_prompt_and_parses_response(monkeypatch):
    response = httpx.Response(200, json={"model": "model-from-response", "choices": [{"message": {"content": '{"status":"supported","reasoning":"The passage matches.","passage_indexes":[1]}'}}], "usage": {"prompt_tokens": 52, "completion_tokens": 19}})
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    cfg = ProviderConfig(provider="custom", base_url="https://provider.example/v1", model="model-123", api_key="fake")
    reply = chat(cfg, "Only assess evidence.", "claim and passages")
    parsed = parse_json_reply(reply.text)
    assert parsed["status"] == "supported"
    assert reply.total_tokens == 71
    assert reply.model == "model-from-response"


def test_local_provider_disables_hidden_reasoning(monkeypatch):
    captured: dict = {}

    def fake_request(cfg, method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"model": "qwen3", "choices": [{"message": {"content": '{"status":"supported"}'}}], "usage": {}})

    monkeypatch.setattr(adapters, "_request", fake_request)
    chat(ProviderConfig(provider="ollama", base_url="http://127.0.0.1:11434/v1", model="qwen3"), "system", "user")
    assert captured["json"]["reasoning_effort"] == "none"


def test_cloud_provider_keeps_model_default_reasoning(monkeypatch):
    captured: dict = {}

    def fake_request(cfg, method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"model": "gpt-4o", "choices": [{"message": {"content": '{"status":"supported"}'}}], "usage": {}})

    monkeypatch.setattr(adapters, "_request", fake_request)
    chat(ProviderConfig(provider="openai", api_key="fake", model="gpt-4o"), "system", "user")
    assert "reasoning_effort" not in captured["json"]


def test_empty_or_malformed_provider_responses_fail_safely(monkeypatch):
    response = httpx.Response(200, json={"choices": []})
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    cfg = ProviderConfig(provider="custom", base_url="https://provider.example/v1", model="model", api_key="fake")
    with pytest.raises(ProviderError, match="empty or malformed"):
        chat(cfg, "system", "user")
    with pytest.raises(ProviderError, match="valid JSON"):
        parse_json_reply("not json")


def test_provider_catalog_exposes_every_supported_provider(client):
    response = client.get("/api/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert {item["id"] for item in providers} == {"local", "openai", "anthropic", "openrouter", "custom", "ollama", "lm_studio"}
    for item in providers:
        assert item["label"]
        assert item["cost_tier"] in {"free", "usage", "varies"}
        assert isinstance(item["key_required"], bool)
        assert isinstance(item["setup"], list)


def test_reasoning_only_response_reports_actionable_error(monkeypatch):
    response = httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "", "reasoning": "thinking…"}}], "usage": {}})
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    cfg = ProviderConfig(provider="ollama", base_url="http://127.0.0.1:11434/v1", model="qwen3")
    with pytest.raises(ProviderError, match="internal reasoning"):
        chat(cfg, "system", "user")


def test_think_tags_and_surrounding_prose_do_not_break_json_parsing(monkeypatch):
    response = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "answer{\"status\":\"supported\"}"}}], "usage": {}})
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    cfg = ProviderConfig(provider="ollama", base_url="http://127.0.0.1:11434/v1", model="qwen3")
    reply = chat(cfg, "system", "user")
    assert parse_json_reply(reply.text)["status"] == "supported"


def test_parse_json_reply_extracts_object_from_surrounding_prose():
    assert parse_json_reply('Here is the result: {"status": "contradicted", "reasoning": "no"} done')["status"] == "contradicted"


def test_model_discovery_prefers_local_model_names(monkeypatch):
    response = httpx.Response(200, json={"data": [{"id": "gemma3:4b"}, {"id": "other-model"}]})
    monkeypatch.setattr(adapters, "_request", lambda *args, **kwargs: response)
    result = check_provider(ProviderConfig(provider="ollama", base_url="http://127.0.0.1:11434/v1"))
    assert result["suggested_model"] == "gemma3:4b"


def test_parse_json_reply_recovers_first_balanced_object_past_stray_braces():
    text = '{"status":"supported","reasoning":"braces { inside } string"} trailing } noise'
    assert parse_json_reply(text)["status"] == "supported"


def test_parse_json_reply_reports_truncated_reply_actionably():
    with pytest.raises(ProviderError, match="cut off by the output-token limit"):
        parse_json_reply('{"status": "supported", "reasoning": "because the passage')


def test_parse_json_reply_handles_missing_input():
    with pytest.raises(ProviderError, match="valid JSON"):
        parse_json_reply("")
