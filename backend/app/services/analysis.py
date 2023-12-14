from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import Analysis, Citation, Claim, Evidence, Source
from app.providers.base import provider_from_record
from app.providers.usage import record_usage, remaining_daily_tokens
from app.security.url_fetch import UnsafeURLError, fetch_public_source
from app.services.citations import CitationMention, normalize_url, parse_citations
from app.services.claims import ClaimCandidate, extract_claims
from app.services.evidence import Assessment, assess_claim
from app.services.metrics import status_counts
from app.services.retrieval import Passage, content_hash, rank_passages

logger = logging.getLogger("verity.analysis")


def _set_status(analysis: Analysis, status: str, progress: int | None = None) -> None:
    analysis.status = status
    if progress is not None:
        analysis.progress = progress
    analysis.updated_at = datetime.now(UTC)


def _source_by_url(sources: list[Source], url: str) -> Source | None:
    target = normalize_url(url)
    return next((source for source in sources if source.url and (normalize_url(source.url) == target or normalize_url(str(source.metadata_json.get("requested_url", ""))) == target)), None)


def _source_by_external_id(sources: list[Source], external_id: str | None) -> Source | None:
    if not external_id:
        return None
    return next((source for source in sources if source.external_id and source.external_id.casefold() == external_id.casefold()), None)


def _citation_mentions_for_claim(mentions: list[CitationMention], candidate: ClaimCandidate, input_text: str) -> list[CitationMention]:
    selected = [m for m in mentions if candidate.start_char <= m.start_char < candidate.end_char]
    # A trailing citation may follow the final predicate in a sentence that was
    # split into atomic claims. Share it only when no sentence boundary intervenes.
    if not selected:
        tail_mentions = [m for m in mentions if candidate.end_char <= m.start_char and m.kind in {"numbered_reference", "unresolved_reference", "source_id", "markdown_link", "url", "doi", "named_reference"}]
        nearest = min(tail_mentions, key=lambda item: item.start_char, default=None)
        if nearest:
            gap = input_text[candidate.end_char:nearest.start_char]
            if not re.search(r"[.!?\n\r]", gap):
                selected = [nearest]
    unique: dict[tuple[str | None, str], CitationMention] = {}
    for item in selected:
        unique[(item.url, item.raw)] = item
    return list(unique.values())


def _title_mismatch(raw: str, title: str) -> bool:
    label = re.match(r"\[([^\]]+)\]", raw)
    if not label or not title:
        return False
    visible = label.group(1).strip().lower()
    if len(visible) < 5 or visible.startswith("http"):
        return False
    return SequenceMatcher(None, visible, title.casefold()).ratio() < 0.24


def _resolve_mention(session: Session, mention: CitationMention, sources: list[Source], fetched_urls: set[str], analysis: Analysis) -> tuple[Source | None, Citation]:
    source = _source_by_external_id(sources, mention.external_id)
    if mention.url:
        source = source or _source_by_url(sources, mention.url)
        normalized = normalize_url(mention.url)
        if source is None and normalized not in fetched_urls:
            fetched_urls.add(normalized)
            if len(fetched_urls) <= 20:
                try:
                    page = fetch_public_source(mention.url, max_bytes=config.max_source_bytes, max_chars=config.max_input_chars)
                    source = Source(analysis_id=analysis.id, title=page.title[:500] or page.url, url=page.url, source_type="web", status="retrieved", content=page.text, content_hash=content_hash(page.text), retrieved_at=datetime.now(UTC), metadata_json={"content_type": page.content_type, "redirect_count": page.redirect_count, "requested_url": mention.url})
                    session.add(source)
                    session.flush()
                    sources.append(source)
                except (UnsafeURLError, ValueError) as exc:
                    source = Source(analysis_id=analysis.id, title=mention.raw[:300] or mention.url, url=mention.url, source_type="web", status="unavailable", error=str(exc)[:500], content=None, metadata_json={"requested_url": mention.url})
                    session.add(source)
                    session.flush()
                    sources.append(source)
            else:
                source = Source(analysis_id=analysis.id, title=mention.url[:300], url=mention.url, source_type="web", status="unavailable", error="Per-analysis source retrieval limit reached (20 unique URLs).", metadata_json={"requested_url": mention.url})
                session.add(source)
                session.flush()
                sources.append(source)
        elif source is None and normalized in fetched_urls:
            source = _source_by_url(sources, normalized)
    if source and source.status in {"provided", "retrieved"} and source.content:
        resolution = "resolved"
    elif source and source.status == "unavailable":
        resolution = "unavailable"
    elif mention.kind == "source_id" and not source:
        resolution = "unresolved"
    elif mention.url and not source:
        resolution = "unavailable"
    else:
        resolution = "unresolved"
    citation = Citation(claim_id="", source_id=source.id if source else None, raw=mention.raw[:1000], url=mention.url, kind=mention.kind, resolution_status=resolution, metadata_json={"external_id": mention.external_id, "title_mismatch": _title_mismatch(mention.raw, source.title) if source else False})
    return source, citation


def _sources_for_claim(citations: list[Citation], sources: list[Source], mode: str) -> tuple[list[Source], bool, bool]:
    cited_ids = {citation.source_id for citation in citations if citation.source_id}
    has_citation = bool(citations)
    if mode == "evidence_discovery":
        candidates = [source for source in sources if source.content and source.status in {"provided", "retrieved"}]
    else:
        candidates = [source for source in sources if source.id in cited_ids and source.content and source.status in {"provided", "retrieved"}]
    unavailable = bool(citations) and not candidates and any(c.resolution_status in {"unavailable", "unresolved"} for c in citations)
    return candidates, has_citation, unavailable


def _assessment_passages(candidate_sources: list[Source], claim_text: str) -> list[Passage]:
    tuples = [(source.id, source.title, source.url, source.content or "") for source in candidate_sources]
    ranked = rank_passages(claim_text, tuples, top_k=5)
    return [passage for passage in ranked if passage.score >= 0.025]


def process_analysis(session: Session, analysis_id: str) -> None:
    analysis = session.get(Analysis, analysis_id)
    if not analysis or analysis.status in {"completed", "cancelled"}:
        return
    if analysis.cancel_requested:
        _set_status(analysis, "cancelled", 100)
        session.commit()
        return
    _set_status(analysis, "running", 2)
    analysis.error = None
    analysis.completed_at = None
    # Reruns are deterministic snapshots; remove old claim outputs while preserving input sources.
    analysis.claims.clear()
    session.commit()
    try:
        candidates = extract_claims(analysis.input_text, max_claims=min(config.max_claims, int(analysis.settings_json.get("max_claims", 80))))
        mentions = parse_citations(analysis.input_text)
        sources = list(session.scalars(select(Source).where(Source.analysis_id == analysis.id)).all())
        for source in sources:
            if source.content:
                source.content_hash = source.content_hash or content_hash(source.content)
                if source.status == "provided":
                    source.retrieved_at = source.retrieved_at or datetime.now(UTC)
        session.commit()

        _set_status(analysis, "running", 12)
        session.commit()
        fetched_urls: set[str] = set()
        # Resolve all citations before classifying any claim; duplicates share a source record.
        claim_mentions = [_citation_mentions_for_claim(mentions, candidate, analysis.input_text) for candidate in candidates]
        citation_map: list[list[Citation]] = []
        for candidate, claim_mentions_list in zip(candidates, claim_mentions, strict=False):
            claim = Claim(analysis_id=analysis.id, ordinal=len(citation_map) + 1, text=candidate.text, normalized_text=candidate.normalized_text, start_char=candidate.start_char, end_char=candidate.end_char, kind=candidate.kind, status="needs_human_review", reasoning="Assessment pending.", assessor="deterministic-local-v1", uncertainty="high", assessment_meta={})
            session.add(claim)
            session.flush()
            attached: list[Citation] = []
            for mention in claim_mentions_list:
                _resolved_source, citation = _resolve_mention(session, mention, sources, fetched_urls, analysis)
                citation.claim_id = claim.id
                session.add(citation)
                attached.append(citation)
            citation_map.append(attached)
            # Keep references fresh for later claims that may reuse a fetched source.
            session.flush()
        session.commit()

        provider = provider_from_record(session, analysis.owner_id)
        provider_target = analysis.settings_json.get("provider_target", {})
        target_mismatch = analysis.use_ai and (provider_target.get("provider") != provider.provider or provider_target.get("base_url") != provider.base_url or provider_target.get("model") != provider.model)
        ai_enabled = analysis.use_ai and not target_mismatch
        if target_mismatch:
            logger.warning("analysis.provider_target_changed", extra={"analysis_id": analysis.id, "provider": provider.provider})
        provider_label = provider.provider if ai_enabled else "local"
        analysis.provider = provider_label
        analysis.settings_json = {**analysis.settings_json, "provider": provider.provider, "model": provider.model, "local_models": config.enable_local_models}
        analysis.result_meta = {"pipeline_version": "0.1.0", "assessor_mode": "local_rules" if not ai_enabled or provider.provider == "local" else "optional_provider_plus_local_fallback", "provider_skipped": "configuration_changed_after_queueing" if target_mismatch else None, "embedding_enabled": config.enable_local_models, "retrieved_source_count": sum(1 for s in sources if s.content), "source_hashes": {s.id: s.content_hash for s in sources if s.content}, "limitations": "Support classifications evaluate supplied evidence; they do not establish objective truth."}
        session.commit()

        total = max(1, len(candidates))
        analysis_budget = provider.analysis_token_budget
        daily_remaining = remaining_daily_tokens(session, analysis.owner_id, provider.daily_token_budget) if ai_enabled else 0
        initial_provider_budget = min(analysis_budget, daily_remaining)
        provider_tokens_used = 0
        for index, (candidate, citations) in enumerate(zip(candidates, citation_map, strict=False), start=1):
            session.refresh(analysis)
            if analysis.cancel_requested:
                _set_status(analysis, "cancelled", int((index - 1) * 100 / total))
                session.commit()
                return
            current_claim = session.scalar(select(Claim).where(Claim.analysis_id == analysis.id, Claim.ordinal == index))
            if not current_claim:
                continue
            if candidate.kind == "not_factual":
                assessment = Assessment("not_applicable", "This span is a question, instruction, opinion, or non-propositional text rather than an independently checkable factual claim.", "deterministic-local-v1", "not_applicable", {})
                passages: list[Passage] = []
            else:
                candidate_sources, has_citation, unavailable = _sources_for_claim(citations, sources, analysis.mode)
                passages = _assessment_passages(candidate_sources, candidate.normalized_text)
                if not passages and analysis.mode == "evidence_discovery" and not has_citation and not candidate_sources:
                    assessment = Assessment("citation_missing", "No citation was supplied and no independent evidence source was attached for discovery.", "deterministic-local-v1", "high", {})
                else:
                    available_budget = max(0, initial_provider_budget - provider_tokens_used)
                    assessment = assess_claim(candidate.normalized_text, passages, has_citation, unavailable, analysis.mode, provider, ai_enabled, available_budget)
                    if assessment.metadata.get("provider_tokens"):
                        used = int(assessment.metadata["provider_tokens"])
                        provider_tokens_used += used
                        record_usage(session, analysis.owner_id, used)
                current_claim.status = assessment.status
                current_claim.reasoning = assessment.reasoning
                current_claim.assessor = assessment.assessor
                current_claim.uncertainty = assessment.uncertainty
                current_claim.assessment_meta = assessment.metadata
            if candidate.kind == "not_factual":
                current_claim.status = assessment.status
                current_claim.reasoning = assessment.reasoning
                current_claim.assessor = assessment.assessor
                current_claim.uncertainty = assessment.uncertainty
                current_claim.assessment_meta = assessment.metadata
            for rank, passage in enumerate(passages[:5], start=1):
                # No generated quotation: this text is a bounded exact slice of stored source content.
                session.add(Evidence(claim_id=current_claim.id, source_id=passage.source_id, passage_text=passage.text, start_char=passage.start_char, end_char=passage.end_char, page=passage.page, section=passage.section, relevance=passage.score, rank=rank, content_hash=passage.fingerprint))
            _set_status(analysis, "running", 20 + int(index * 75 / total))
            if index % 5 == 0 or index == total:
                session.commit()
        session.refresh(analysis)
        if analysis.cancel_requested:
            _set_status(analysis, "cancelled", 100)
        else:
            _set_status(analysis, "completed", 100)
        analysis.completed_at = datetime.now(UTC)
        analysis.error = None
        persisted_claims = list(session.scalars(select(Claim).where(Claim.analysis_id == analysis.id).order_by(Claim.ordinal)).all())
        analysis.result_meta = {**analysis.result_meta, "status_counts": status_counts(persisted_claims), "provider_token_usage_estimate_or_reported": provider_tokens_used, "provider_budget_tokens": initial_provider_budget}
        session.commit()
        logger.info("analysis.completed", extra={"analysis_id": analysis.id, "claim_count": len(candidates), "status": analysis.status})
    except Exception as exc:
        session.rollback()
        failed = session.get(Analysis, analysis_id)
        if failed:
            _set_status(failed, "failed", 100)
            # Avoid storing full source/provider exception bodies in UI or logs.
            failed.error = f"Analysis failed ({type(exc).__name__}). Review input limits and server logs."
            failed.completed_at = datetime.now(UTC)
            session.commit()
        logger.error("analysis.failed", extra={"analysis_id": analysis_id, "error_type": type(exc).__name__})
