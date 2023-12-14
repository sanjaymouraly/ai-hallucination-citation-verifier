from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mode = Literal["citation_audit", "evidence_discovery"]
ProviderName = Literal["local", "openai", "anthropic", "openrouter", "custom", "ollama", "lm_studio"]


class EvidenceInput(BaseModel):
    id: str | None = Field(default=None, max_length=120)
    title: str = Field(default="User-provided evidence", max_length=500)
    url: str | None = Field(default=None, max_length=2048)
    content: str = Field(min_length=1, max_length=500_000)
    source_type: Literal["provided", "rag", "document"] = "provided"

    @field_validator("url")
    @classmethod
    def trim_url(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        from urllib.parse import urlsplit
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Source URL must be HTTP(S) and must not include credentials")
        return normalized


class AnalysisCreate(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    title: str | None = Field(default=None, max_length=240)
    mode: Mode = "citation_audit"
    sources: list[EvidenceInput] = Field(default_factory=list, max_length=20)
    use_ai: bool = False
    confirm_external_processing: bool = False
    max_claims: int = Field(default=80, ge=1, le=120)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must contain at least one non-whitespace character")
        return value


class BatchItem(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    title: str | None = Field(default=None, max_length=240)
    mode: Mode = "citation_audit"
    sources: list[EvidenceInput] = Field(default_factory=list, max_length=20)


class BatchCreate(BaseModel):
    items: list[BatchItem] = Field(min_length=1, max_length=25)
    use_ai: bool = False
    confirm_external_processing: bool = False

    @model_validator(mode="after")
    def bounded_aggregate_content(self) -> BatchCreate:
        total_bytes = sum(len(item.text.encode("utf-8")) + sum(len(source.content.encode("utf-8")) for source in item.sources) for item in self.items)
        if total_bytes > 25 * 1024 * 1024:
            raise ValueError("The aggregate text and source content in a batch cannot exceed 25 MiB.")
        return self


class ProviderConfigInput(BaseModel):
    provider: ProviderName = "local"
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False
    model: str | None = Field(default=None, max_length=200)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=8192, ge=32, le=8192)
    timeout_seconds: int = Field(default=30, ge=3, le=180)
    retries: int = Field(default=2, ge=0, le=5)
    analysis_token_budget: int = Field(default=10000, ge=100, le=1_000_000)
    daily_token_budget: int = Field(default=50000, ge=100, le=10_000_000)

    @field_validator("base_url")
    @classmethod
    def safe_base_url(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if value and not value.startswith(("http://", "https://")):
                raise ValueError("Base URL must start with http:// or https://")
        return value or None


class ReviewCreate(BaseModel):
    decision: Literal["supported", "partially_supported", "contradicted", "insufficient_evidence", "needs_more_evidence", "not_applicable"]
    notes: str = Field(default="", max_length=5000)
    reviewer: str = Field(default="reviewer", min_length=1, max_length=120)


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    mode: str
    status: str
    progress: int
    provider: str
    use_ai: bool
    created_at: str
    updated_at: str
    completed_at: str | None = None
    total_claims: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class CompareRequest(BaseModel):
    left_id: str
    right_id: str
