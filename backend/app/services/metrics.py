from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.models import Analysis, Claim

STATUS_KEYS = ["supported", "partially_supported", "contradicted", "insufficient_evidence", "citation_missing", "source_unavailable", "needs_human_review", "not_applicable"]


def status_counts(claims: list[Claim]) -> dict[str, int]:
    values = Counter(claim.status for claim in claims)
    return {key: values.get(key, 0) for key in STATUS_KEYS}


def analysis_summary(analysis: Analysis) -> dict:
    counts = status_counts(analysis.claims)
    return {
        "id": analysis.id,
        "title": analysis.title,
        "mode": analysis.mode,
        "status": analysis.status,
        "progress": analysis.progress,
        "provider": analysis.provider,
        "use_ai": analysis.use_ai,
        "created_at": analysis.created_at.isoformat(),
        "updated_at": analysis.updated_at.isoformat(),
        "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
        "total_claims": len(analysis.claims),
        "status_counts": counts,
        "error": analysis.error,
        "batch_id": analysis.batch_id,
    }


def dashboard_data(session: Session, owner_id: str) -> dict:
    analyses = session.query(Analysis).filter(Analysis.owner_id == owner_id).order_by(Analysis.created_at.desc()).limit(8).all()
    claims = session.query(Claim).join(Analysis).filter(Analysis.owner_id == owner_id).all()
    pending = session.query(Claim).join(Analysis).filter(Analysis.owner_id == owner_id, Claim.status == "needs_human_review").count()
    return {"recent": [analysis_summary(item) for item in analyses], "total_analyses": session.query(Analysis).filter(Analysis.owner_id == owner_id).count(), "total_claims": len(claims), "status_counts": status_counts(claims), "pending_reviews": pending}
