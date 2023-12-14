from __future__ import annotations

from typing import Any

# Static, non-secret metadata that powers the "Easy connect" provider picker and
# the per-provider cost/credential guidance. Secrets are never stored here.
PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "local",
        "label": "Local deterministic",
        "tagline": "Built-in rules",
        "description": "Deterministic, local rules. No provider request, model download, or paid API is required.",
        "base_url": None,
        "auth": "none",
        "key_required": False,
        "key_placeholder": "",
        "key_help": "No API key is used.",
        "model_placeholder": "Not used by deterministic local rules",
        "model_help": "The local assessor does not call a model.",
        "cost_tier": "free",
        "cost_note": "Free. Runs entirely on this machine.",
        "setup": ["Select Local deterministic mode", "Save settings", "Run an analysis"],
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "tagline": "Local models",
        "description": "Ollama local OpenAI-compatible endpoint. Runs models such as gemma or qwen on this machine.",
        "base_url": "http://127.0.0.1:11434/v1",
        "auth": "none",
        "key_required": False,
        "key_placeholder": "",
        "key_help": "No API key is required for a local Ollama server.",
        "model_placeholder": "gemma3, qwen3.5, llama3…",
        "model_help": "Use Test connection to list the models installed in Ollama.",
        "cost_tier": "free",
        "cost_note": "Free. Uses models already installed in Ollama on this machine.",
        "setup": ["Install a model with `ollama pull gemma3`", "Keep the Ollama server running", "Select Ollama and test the connection"],
    },
    {
        "id": "openai",
        "label": "OpenAI API",
        "tagline": "ChatGPT models",
        "description": "OpenAI official API. A ChatGPT subscription is separate from API access and billing.",
        "base_url": "https://api.openai.com/v1",
        "auth": "bearer",
        "key_required": True,
        "key_placeholder": "sk-…",
        "key_help": "Create an API key at platform.openai.com/api-keys.",
        "model_placeholder": "gpt-4o-mini",
        "model_help": "Use Test connection to list the model IDs available to your key.",
        "cost_tier": "usage",
        "cost_note": "Paid per token. Review OpenAI pricing before bulk use.",
        "setup": ["Create an OpenAI API key", "Paste the key", "Test the connection to discover models"],
    },
    {
        "id": "anthropic",
        "label": "Anthropic Claude API",
        "tagline": "Claude models",
        "description": "Anthropic Claude official API. Uses the Messages API with an x-api-key header.",
        "base_url": "https://api.anthropic.com/v1",
        "auth": "x-api-key",
        "key_required": True,
        "key_placeholder": "sk-ant-…",
        "key_help": "Create a key at console.anthropic.com.",
        "model_placeholder": "claude-sonnet-4-5",
        "model_help": "Use Test connection to list the model IDs available to your key.",
        "cost_tier": "usage",
        "cost_note": "Paid per token. Review Anthropic pricing before bulk use.",
        "setup": ["Create an Anthropic API key", "Paste the key", "Test the connection to discover models"],
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "tagline": "Many providers",
        "description": "OpenRouter API. One key reaches many models; pricing depends on the selected model.",
        "base_url": "https://openrouter.ai/api/v1",
        "auth": "bearer",
        "key_required": True,
        "key_placeholder": "sk-or-…",
        "key_help": "Create a key at openrouter.ai/keys.",
        "model_placeholder": "openai/gpt-4o-mini",
        "model_help": "Use Test connection to list the model IDs available to your key.",
        "cost_tier": "usage",
        "cost_note": "Paid per token, varies by model. Check the model page before bulk use.",
        "setup": ["Create an OpenRouter key", "Paste the key", "Test the connection to discover models"],
    },
    {
        "id": "custom",
        "label": "Custom OpenAI-compatible",
        "tagline": "Your endpoint",
        "description": "Any OpenAI-compatible endpoint (vLLM, LocalAI, Azure, a gateway, or your own server).",
        "base_url": None,
        "auth": "bearer",
        "key_required": False,
        "key_placeholder": "Usually required",
        "key_help": "Enter a key if your endpoint requires one; leave blank if it is open.",
        "model_placeholder": "your-model-id",
        "model_help": "Use the model identifier your endpoint expects.",
        "cost_tier": "varies",
        "cost_note": "Cost depends on the endpoint you configure. Use HTTPS for multi-user deployments.",
        "setup": ["Enter your endpoint base URL", "Add a key if required", "Test the connection"],
    },
    {
        "id": "lm_studio",
        "label": "LM Studio",
        "tagline": "Local models",
        "description": "LM Studio local OpenAI-compatible endpoint. Keep its local server access restricted.",
        "base_url": "http://127.0.0.1:1234/v1",
        "auth": "none",
        "key_required": False,
        "key_placeholder": "",
        "key_help": "No API key is required for a local LM Studio server.",
        "model_placeholder": "local-model",
        "model_help": "Use Test connection to list the models loaded in LM Studio.",
        "cost_tier": "free",
        "cost_note": "Free. Uses models loaded in LM Studio on this machine.",
        "setup": ["Load a model in LM Studio", "Start the local server", "Select LM Studio and test the connection"],
    },
]

CATALOG_BY_ID = {entry["id"]: entry for entry in PROVIDER_CATALOG}


def provider_catalog() -> list[dict[str, Any]]:
    """Return a fresh copy so callers cannot mutate module state."""
    return [dict(entry) for entry in PROVIDER_CATALOG]


def provider_preset(provider: str) -> dict[str, Any] | None:
    entry = CATALOG_BY_ID.get(provider)
    return dict(entry) if entry else None
