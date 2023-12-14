from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (Index("ix_analyses_owner_created", "owner_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(120), nullable=False, default="local", index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="Untitled verification")
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="citation_audit")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider: Mapped[str] = mapped_column(String(48), nullable=False, default="local")
    use_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    claims: Mapped[list[Claim]] = relationship(back_populates="analysis", cascade="all, delete-orphan", order_by="Claim.ordinal")
    sources: Mapped[list[Source]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_analysis_url", "analysis_id", "url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="Untitled source")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, default="provided")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="provided")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    analysis: Mapped[Analysis] = relationship(back_populates="sources")
    citations: Mapped[list[Citation]] = relationship(back_populates="source")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="source")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("analysis_id", "ordinal", name="uq_claim_analysis_ordinal"), Index("ix_claims_status", "status"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="factual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="needs_human_review")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessor: Mapped[str] = mapped_column(String(120), nullable=False, default="deterministic-local-v1")
    uncertainty: Mapped[str] = mapped_column(String(24), nullable=False, default="high")
    assessment_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    analysis: Mapped[Analysis] = relationship(back_populates="claims")
    citations: Mapped[list[Citation]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="claim", cascade="all, delete-orphan", order_by="Evidence.rank")
    reviews: Mapped[list[Review]] = relationship(back_populates="claim", cascade="all, delete-orphan", order_by="Review.created_at")


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True)
    raw: Mapped[str] = mapped_column(String(1000), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="url")
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    claim: Mapped[Claim] = relationship(back_populates="citations")
    source: Mapped[Source | None] = relationship(back_populates="citations")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    passage_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(240), nullable=True)
    relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    claim: Mapped[Claim] = relationship(back_populates="evidence")
    source: Mapped[Source] = relationship(back_populates="evidence")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewer: Mapped[str] = mapped_column(String(120), nullable=False, default="reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    claim: Mapped[Claim] = relationship(back_populates="reviews")


class ProviderSetting(Base):
    __tablename__ = "provider_settings"

    owner_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    provider: Mapped[str] = mapped_column(String(48), nullable=False, default="local")
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    analysis_token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    daily_token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=50000)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ProviderUsage(Base):
    __tablename__ = "provider_usage"
    __table_args__ = (UniqueConstraint("owner_id", "usage_date", name="uq_provider_usage_owner_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    usage_date: Mapped[str] = mapped_column(String(10), nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
