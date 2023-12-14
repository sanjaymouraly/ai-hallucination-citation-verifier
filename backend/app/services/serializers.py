from __future__ import annotations

from app.models import Analysis, Review
from app.services.metrics import analysis_summary


def _review_json(review: Review) -> dict:
    return {"id": review.id, "decision": review.decision, "notes": review.notes, "reviewer": review.reviewer, "created_at": review.created_at.isoformat()}


def analysis_detail(analysis: Analysis) -> dict:
    sources = {source.id: source for source in analysis.sources}
    claims: list[dict] = []
    for claim in analysis.claims:
        citations = []
        for citation in claim.citations:
            source = sources.get(citation.source_id) if citation.source_id else citation.source
            citations.append({"id": citation.id, "raw": citation.raw, "url": citation.url, "kind": citation.kind, "resolution_status": citation.resolution_status, "title_mismatch": bool(citation.metadata_json.get("title_mismatch")), "source": {"id": source.id, "title": source.title, "url": source.url, "status": source.status, "error": source.error} if source else None})
        evidence = []
        for item in claim.evidence:
            source = sources.get(item.source_id) or item.source
            evidence.append({"id": item.id, "source_id": item.source_id, "source_title": source.title if source else "Unknown source", "source_url": source.url if source else None, "page": item.page, "section": item.section, "text": item.passage_text, "start_char": item.start_char, "end_char": item.end_char, "relevance": round(item.relevance, 4), "rank": item.rank, "content_hash": item.content_hash})
        claims.append({"id": claim.id, "ordinal": claim.ordinal, "text": claim.text, "normalized_text": claim.normalized_text, "start_char": claim.start_char, "end_char": claim.end_char, "kind": claim.kind, "status": claim.status, "reasoning": claim.reasoning, "assessor": claim.assessor, "uncertainty": claim.uncertainty, "assessment_meta": claim.assessment_meta, "citations": citations, "evidence": evidence, "reviews": [_review_json(review) for review in claim.reviews]})
    source_rows = [{"id": source.id, "external_id": source.external_id, "title": source.title, "url": source.url, "source_type": source.source_type, "status": source.status, "error": source.error, "content_hash": source.content_hash, "retrieved_at": source.retrieved_at.isoformat() if source.retrieved_at else None, "characters": len(source.content or ""), "metadata": source.metadata_json} for source in analysis.sources]
    return {**analysis_summary(analysis), "input_text": analysis.input_text, "settings": analysis.settings_json, "result_meta": analysis.result_meta, "sources": source_rows, "claims": claims}
