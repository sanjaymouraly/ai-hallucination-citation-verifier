from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProviderUsage


def estimate_tokens(text: str) -> int:
    # Approximation for budgeting only; not billed token usage.
    return max(1, (len(text) + 3) // 4)


def remaining_daily_tokens(session: Session, owner_id: str, daily_budget: int) -> int:
    today = datetime.now(UTC).date().isoformat()
    row = session.scalar(select(ProviderUsage).where(ProviderUsage.owner_id == owner_id, ProviderUsage.usage_date == today))
    return max(0, daily_budget - (row.estimated_tokens if row else 0))


def record_usage(session: Session, owner_id: str, tokens: int) -> None:
    today = datetime.now(UTC).date().isoformat()
    row = session.scalar(select(ProviderUsage).where(ProviderUsage.owner_id == owner_id, ProviderUsage.usage_date == today))
    if not row:
        row = ProviderUsage(owner_id=owner_id, usage_date=today, estimated_tokens=0, request_count=0)
        session.add(row)
        session.flush()
    row.estimated_tokens += max(0, tokens)
    row.request_count += 1
    session.flush()
