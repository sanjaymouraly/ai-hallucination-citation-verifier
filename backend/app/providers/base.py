from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import ProviderSetting
from app.security.crypto import decrypt_secret


class ProviderError(RuntimeError):
    """Safe-to-display provider error. Never include request bodies or credentials."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "local"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float = 0.0
    max_output_tokens: int = 8192
    timeout_seconds: int = 30
    retries: int = 2
    analysis_token_budget: int = 10_000
    daily_token_budget: int = 50_000

    @property
    def is_remote(self) -> bool:
        return self.provider not in {"local", "ollama", "lm_studio"}


# Ephemeral key storage is process-memory only when no encryption key is configured.
runtime_secrets: dict[str, str] = {}


def provider_from_record(session: Session, owner_id: str) -> ProviderConfig:
    saved = session.get(ProviderSetting, owner_id)
    if not saved:
        return ProviderConfig()
    env_key = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "openrouter": os.getenv("OPENROUTER_API_KEY"),
        "custom": os.getenv("CUSTOM_AI_API_KEY"),
    }.get(saved.provider)
    key = env_key or runtime_secrets.get(owner_id) or decrypt_secret(saved.encrypted_api_key)
    return ProviderConfig(
        provider=saved.provider,
        base_url=saved.base_url,
        api_key=key,
        model=saved.model,
        temperature=saved.temperature,
        max_output_tokens=saved.max_output_tokens,
        timeout_seconds=saved.timeout_seconds,
        retries=saved.retries,
        analysis_token_budget=saved.analysis_token_budget,
        daily_token_budget=saved.daily_token_budget,
    )


def provider_config_from_payload(data: Any) -> ProviderConfig:
    return ProviderConfig(
        provider=data.provider,
        base_url=data.base_url,
        api_key=data.api_key,
        model=data.model,
        temperature=data.temperature,
        max_output_tokens=data.max_output_tokens,
        timeout_seconds=data.timeout_seconds,
        retries=data.retries,
        analysis_token_budget=data.analysis_token_budget,
        daily_token_budget=data.daily_token_budget,
    )
