from __future__ import annotations

import csv
import html
import io
import json
import logging
import os
import re
import secrets
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import config
from app.models import Analysis, Citation, Claim, Evidence, ProviderSetting, ProviderUsage, Review, Source
from app.providers.adapters import test_provider
from app.providers.base import provider_config_from_payload, provider_from_record, runtime_secrets
from app.providers.catalog import provider_catalog
from app.providers.usage import remaining_daily_tokens
from app.schemas import AnalysisCreate, BatchCreate, CompareRequest, EvidenceInput, ProviderConfigInput, ReviewCreate
from app.security.crypto import decrypt_secret, encrypt_secret
from app.services.files import DocumentReadError, extract_document
from app.services.metrics import analysis_summary, dashboard_data
from app.services.serializers import analysis_detail

logger = logging.getLogger("verity.api")
router = APIRouter(prefix="/api")


def get_db(request: Request) -> Generator[Session, None, None]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _owner(request: Request) -> str:
    return getattr(request.state, "owner_id", "local")


def _owned_analysis(session: Session, owner_id: str, analysis_id: str) -> Analysis:
    query = select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == owner_id).options(
        selectinload(Analysis.claims).selectinload(Claim.citations).selectinload(Citation.source),
        selectinload(Analysis.claims).selectinload(Claim.evidence).selectinload(Evidence.source),
        selectinload(Analysis.claims).selectinload(Claim.reviews),
        selectinload(Analysis.sources),
    )
    analysis = session.scalar(query)
    if analysis is None:
        raise HTTPException(404, "Analysis not found.")
    return analysis


def _external_ai_consent_required(session: Session, owner_id: str) -> bool:
    # Every non-deterministic provider needs an explicit per-job consent, including
    # Ollama/LM Studio endpoints that may be configured to a remote host.
    return provider_from_record(session, owner_id).provider != "local"


def _check_confirmation(session: Session, owner_id: str, use_ai: bool, confirmed: bool) -> None:
    if use_ai and _external_ai_consent_required(session, owner_id) and not confirmed:
        raise HTTPException(400, "Confirm that claim text and retrieved evidence may be sent to the configured AI provider before enabling AI-assisted review.")


def _new_analysis(session: Session, owner_id: str, text: str, title: str | None, mode: str, source_inputs: list[EvidenceInput], use_ai: bool, batch_id: str | None = None, max_claims: int = 80) -> Analysis:
    if len(text) > config.max_input_chars:
        raise HTTPException(413, f"Input exceeds the configured {config.max_input_chars:,}-character limit; content was not silently truncated.")
    setting = session.get(ProviderSetting, owner_id)
    provider = setting.provider if setting else "local"
    row = Analysis(owner_id=owner_id, batch_id=batch_id, title=(title or _title_from_text(text))[:240], input_text=text, mode=mode, status="queued", progress=0, provider=provider if use_ai else "local", use_ai=use_ai, settings_json={"max_claims": max_claims, "provider_target": {"provider": setting.provider if setting else "local", "base_url": setting.base_url if setting else None, "model": setting.model if setting else None}}, result_meta={})
    session.add(row)
    session.flush()
    used_ids: set[str] = set()
    for item in source_inputs:
        external_id = item.id.strip() if item.id else None
        if external_id and external_id in used_ids:
            raise HTTPException(422, f"Duplicate source identifier: {external_id}")
        if external_id:
            used_ids.add(external_id)
        row.sources.append(Source(analysis_id=row.id, external_id=external_id, title=item.title.strip() or "User-provided evidence", url=item.url, source_type=item.source_type, status="provided", content=item.content, content_hash=None, retrieved_at=datetime.now(UTC), metadata_json={"user_provided": True}))
    return row


def _title_from_text(text: str) -> str:
    first = re.sub(r"\s+", " ", text).strip()
    return (first[:90] + ("…" if len(first) > 90 else "")) or "Untitled verification"


def _read_upload(upload: UploadFile) -> bytes:
    try:
        content = upload.file.read(config.max_upload_bytes + 1)
    except Exception as exc:
        raise HTTPException(400, "Could not read the uploaded file.") from exc
    if len(content) > config.max_upload_bytes:
        raise HTTPException(413, f"Each uploaded file must be {config.max_upload_bytes // (1024 * 1024)} MB or smaller.")
    return content


@router.get("/auth/status")
def auth_status(request: Request) -> dict:
    return {"required": bool(config.api_tokens), "owner": _owner(request) if not config.api_tokens else None}


@router.get("/dashboard")
def dashboard(request: Request, session: Session = Depends(get_db)) -> dict:
    return dashboard_data(session, _owner(request))


@router.get("/analyses")
def list_analyses(request: Request, session: Session = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), status: str | None = None) -> dict:
    query = select(Analysis).where(Analysis.owner_id == _owner(request))
    if status:
        query = query.where(Analysis.status == status)
    query = query.order_by(desc(Analysis.created_at)).offset(offset).limit(limit).options(selectinload(Analysis.claims))
    rows = list(session.scalars(query).all())
    total = session.scalar(select(Analysis.id).where(Analysis.owner_id == _owner(request)).count()) if False else session.query(Analysis).filter(Analysis.owner_id == _owner(request)).count()
    return {"items": [analysis_summary(row) for row in rows], "total": total, "offset": offset, "limit": limit}


@router.post("/analyses", status_code=202)
def create_analysis(payload: AnalysisCreate, request: Request, session: Session = Depends(get_db)) -> dict:
    owner = _owner(request)
    _check_confirmation(session, owner, payload.use_ai, payload.confirm_external_processing)
    row = _new_analysis(session, owner, payload.text, payload.title, payload.mode, payload.sources, payload.use_ai, max_claims=payload.max_claims)
    session.commit()
    session.refresh(row)
    logger.info("analysis.queued", extra={"analysis_id": row.id, "owner_id": owner, "source_count": len(row.sources)})
    return analysis_summary(row)


@router.post("/analyses/upload", status_code=202)
async def create_analysis_upload(
    request: Request,
    text: str = Form(default=""),
    title: str | None = Form(default=None),
    mode: str = Form(default="citation_audit"),
    use_ai: bool = Form(default=False),
    confirm_external_processing: bool = Form(default=False),
    input_file: UploadFile | None = File(default=None),
    evidence_files: list[UploadFile] = File(default=[]),
    sources_json: str = Form(default="[]"),
    session: Session = Depends(get_db),
) -> dict:
    if mode not in {"citation_audit", "evidence_discovery"}:
        raise HTTPException(422, "Mode must be citation_audit or evidence_discovery.")
    owner = _owner(request)
    _check_confirmation(session, owner, use_ai, confirm_external_processing)
    input_text = text.strip()
    total_file_bytes = 0
    if input_file:
        data = await input_file.read(config.max_upload_bytes + 1)
        if len(data) > config.max_upload_bytes:
            raise HTTPException(413, "Input file exceeds the configured per-file upload-size limit.")
        total_file_bytes += len(data)
        if total_file_bytes > config.max_total_upload_bytes:
            raise HTTPException(413, "Uploaded files exceed the configured aggregate upload-size limit.")
        safe_name = Path((input_file.filename or "input.txt").replace("\\", "/")).name
        try:
            input_text = extract_document(safe_name, data, max_chars=config.max_input_chars)
        except DocumentReadError as exc:
            raise HTTPException(422, str(exc)) from exc
    if not input_text:
        raise HTTPException(422, "Provide text or select a supported document file.")
    if len(input_text) > config.max_input_chars:
        raise HTTPException(413, f"Input exceeds the configured {config.max_input_chars:,}-character limit.")
    source_inputs: list[EvidenceInput] = []
    try:
        parsed_sources = json.loads(sources_json)
        if not isinstance(parsed_sources, list) or len(parsed_sources) > 20:
            raise ValueError("Expected an array with no more than 20 sources.")
        source_inputs.extend(EvidenceInput.model_validate(item) for item in parsed_sources)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Attached source metadata must be a JSON array of valid source objects.") from exc
    if len(evidence_files) + len(source_inputs) > 20:
        raise HTTPException(422, "At most 20 evidence sources can be attached.")
    for index, upload in enumerate(evidence_files, start=1):
        data = await upload.read(config.max_upload_bytes + 1)
        if len(data) > config.max_upload_bytes:
            raise HTTPException(413, f"Evidence file {index} exceeds the configured per-file upload-size limit.")
        total_file_bytes += len(data)
        if total_file_bytes > config.max_total_upload_bytes:
            raise HTTPException(413, "Uploaded files exceed the configured aggregate upload-size limit.")
        safe_name = Path((upload.filename or f"evidence-{index}.txt").replace("\\", "/")).name
        try:
            evidence_text = extract_document(safe_name, data, max_chars=500_000)
        except DocumentReadError as exc:
            raise HTTPException(422, f"Evidence file {safe_name}: {exc}") from exc
        source_inputs.append(EvidenceInput(id=f"S{index}", title=safe_name, content=evidence_text, source_type="document"))
    row = _new_analysis(session, owner, input_text, title or (input_file.filename if input_file else None), mode, source_inputs, use_ai)
    session.commit()
    session.refresh(row)
    return analysis_summary(row)


@router.post("/batches", status_code=202)
def create_batch(payload: BatchCreate, request: Request, session: Session = Depends(get_db)) -> dict:
    owner = _owner(request)
    _check_confirmation(session, owner, payload.use_ai, payload.confirm_external_processing)
    batch_id = secrets.token_hex(16)
    items = []
    for item in payload.items:
        row = _new_analysis(session, owner, item.text, item.title, item.mode, item.sources, payload.use_ai, batch_id=batch_id)
        items.append(row)
    session.commit()
    return {"batch_id": batch_id, "status": "queued", "total": len(items), "items": [analysis_summary(item) for item in items]}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, request: Request, session: Session = Depends(get_db)) -> dict:
    rows = list(session.scalars(select(Analysis).where(Analysis.batch_id == batch_id, Analysis.owner_id == _owner(request)).order_by(Analysis.created_at).options(selectinload(Analysis.claims))).all())
    if not rows:
        raise HTTPException(404, "Batch not found.")
    statuses = {"queued", "running", "completed", "failed", "cancelled"}
    counts = {status: sum(row.status == status for row in rows) for status in statuses}
    return {"batch_id": batch_id, "total": len(rows), "counts": counts, "complete": counts["queued"] == 0 and counts["running"] == 0, "items": [analysis_summary(row) for row in rows]}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, request: Request, session: Session = Depends(get_db)) -> dict:
    return analysis_detail(_owned_analysis(session, _owner(request), analysis_id))


@router.post("/analyses/{analysis_id}/rerun", status_code=202)
def rerun_analysis(analysis_id: str, request: Request, session: Session = Depends(get_db), confirm_external_processing: bool = Query(False)) -> dict:
    owner = _owner(request)
    row = _owned_analysis(session, owner, analysis_id)
    if row.status in {"queued", "running"}:
        raise HTTPException(409, "This analysis is already in progress.")
    _check_confirmation(session, owner, row.use_ai, confirm_external_processing)
    row.status = "queued"
    row.progress = 0
    row.cancel_requested = False
    row.error = None
    row.completed_at = None
    session.commit()
    return analysis_summary(row)


@router.post("/analyses/{analysis_id}/cancel")
def cancel_analysis(analysis_id: str, request: Request, session: Session = Depends(get_db)) -> dict:
    row = _owned_analysis(session, _owner(request), analysis_id)
    if row.status == "queued":
        row.status = "cancelled"
        row.progress = 100
    elif row.status == "running":
        row.cancel_requested = True
    else:
        raise HTTPException(409, "Only queued or running jobs can be cancelled.")
    session.commit()
    return analysis_summary(row)


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, request: Request, session: Session = Depends(get_db)) -> Response:
    row = session.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == _owner(request)))
    if not row:
        raise HTTPException(404, "Analysis not found.")
    if row.status == "running":
        raise HTTPException(409, "Cancel the running job before deleting it.")
    session.delete(row)
    session.commit()
    return Response(status_code=204)


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str, request: Request, session: Session = Depends(get_db)) -> dict:
    claim = session.scalar(select(Claim).join(Analysis).where(Claim.id == claim_id, Analysis.owner_id == _owner(request)).options(selectinload(Claim.citations).selectinload(Citation.source), selectinload(Claim.evidence).selectinload(Evidence.source), selectinload(Claim.reviews)))
    if not claim:
        raise HTTPException(404, "Claim not found.")
    analysis = session.scalar(select(Analysis).where(Analysis.id == claim.analysis_id))
    if analysis is None:
        raise HTTPException(404, "Analysis not found.")
    detail = analysis_detail(_owned_analysis(session, _owner(request), analysis.id))
    return next(item for item in detail["claims"] if item["id"] == claim_id)


@router.get("/reviews")
def review_queue(request: Request, session: Session = Depends(get_db), status: str = "needs_human_review", limit: int = Query(100, ge=1, le=500)) -> dict:
    query = select(Claim).join(Analysis).where(Analysis.owner_id == _owner(request))
    if status == "pending":
        query = query.where(Claim.status == "needs_human_review")
    elif status != "all":
        query = query.where(Claim.status == status)
    rows = list(session.scalars(query.order_by(desc(Analysis.created_at), Claim.ordinal).limit(limit).options(selectinload(Claim.analysis), selectinload(Claim.reviews), selectinload(Claim.evidence).selectinload(Evidence.source))).all())
    items = []
    for claim in rows:
        latest = claim.reviews[-1] if claim.reviews else None
        items.append({"id": claim.id, "analysis_id": claim.analysis_id, "analysis_title": claim.analysis.title, "claim": claim.text, "normalized_claim": claim.normalized_text, "status": claim.status, "reasoning": claim.reasoning, "uncertainty": claim.uncertainty, "reviewed": bool(latest), "latest_review": {"decision": latest.decision, "notes": latest.notes, "reviewer": latest.reviewer, "created_at": latest.created_at.isoformat()} if latest else None, "evidence": [{"source_title": item.source.title if item.source else "Source", "source_url": item.source.url if item.source else None, "text": item.passage_text, "page": item.page} for item in claim.evidence[:2]]})
    return {"items": items, "total": len(items)}


@router.post("/claims/{claim_id}/reviews", status_code=201)
def add_review(claim_id: str, payload: ReviewCreate, request: Request, session: Session = Depends(get_db)) -> dict:
    claim = session.scalar(select(Claim).join(Analysis).where(Claim.id == claim_id, Analysis.owner_id == _owner(request)).options(selectinload(Claim.reviews)))
    if not claim:
        raise HTTPException(404, "Claim not found.")
    review = Review(claim_id=claim.id, decision=payload.decision, notes=payload.notes, reviewer=payload.reviewer)
    session.add(review)
    session.commit()
    session.refresh(review)
    return {"id": review.id, "claim_id": claim.id, "decision": review.decision, "notes": review.notes, "reviewer": review.reviewer, "created_at": review.created_at.isoformat(), "model_status": claim.status}


@router.post("/compare")
def compare_analyses(payload: CompareRequest, request: Request, session: Session = Depends(get_db)) -> dict:
    left = _owned_analysis(session, _owner(request), payload.left_id)
    right = _owned_analysis(session, _owner(request), payload.right_id)
    def key(claim: Claim) -> str:
        return re.sub(r"\W+", " ", claim.normalized_text.casefold()).strip()
    left_map = {key(claim): claim for claim in left.claims}
    right_map = {key(claim): claim for claim in right.claims}
    changes = []
    for normalized in sorted(left_map.keys() | right_map.keys()):
        a, b = left_map.get(normalized), right_map.get(normalized)
        if a is None:
            assert b is not None
            changes.append({"change": "added", "claim": b.text, "old_status": None, "new_status": b.status, "citation_count_delta": len(b.citations)})
        elif b is None:
            changes.append({"change": "removed", "claim": a.text, "old_status": a.status, "new_status": None, "citation_count_delta": -len(a.citations)})
        else:
            latest_a = a.reviews[-1].decision if a.reviews else None
            latest_b = b.reviews[-1].decision if b.reviews else None
            citation_delta = len(b.citations) - len(a.citations)
            if a.status != b.status or citation_delta or latest_a != latest_b:
                changes.append({"change": "changed", "claim": b.text, "old_status": a.status, "new_status": b.status, "old_review": latest_a, "new_review": latest_b, "citation_count_delta": citation_delta})
    return {"left": {"id": left.id, "title": left.title}, "right": {"id": right.id, "title": right.title}, "changes": changes, "unchanged_claims": len(left_map.keys() & right_map.keys()) - sum(item["change"] == "changed" for item in changes)}


def _export_rows(analysis: Analysis) -> list[dict]:
    rows = []
    for claim in analysis.claims:
        rows.append({"claim": claim.text, "normalized_claim": claim.normalized_text, "start_char": claim.start_char, "end_char": claim.end_char, "kind": claim.kind, "status": claim.status, "reasoning": claim.reasoning, "assessor": claim.assessor, "uncertainty": claim.uncertainty, "citations": [{"raw": item.raw, "url": item.url, "resolution_status": item.resolution_status, "source_title": item.source.title if item.source else None} for item in claim.citations], "evidence": [{"text": item.passage_text, "source_title": item.source.title if item.source else None, "source_url": item.source.url if item.source else None, "page": item.page, "start_char": item.start_char, "end_char": item.end_char, "content_hash": item.content_hash} for item in claim.evidence], "reviews": [{"decision": item.decision, "notes": item.notes, "reviewer": item.reviewer, "created_at": item.created_at.isoformat()} for item in claim.reviews]})
    return rows


@router.get("/analyses/{analysis_id}/export")
def export_analysis(analysis_id: str, request: Request, session: Session = Depends(get_db), format: str = Query("json", pattern="^(json|csv|markdown|html)$")) -> Response:
    analysis = _owned_analysis(session, _owner(request), analysis_id)
    rows = _export_rows(analysis)
    filename = f"verity-{analysis.id[:8]}"
    if format == "json":
        import json
        body = json.dumps({"analysis": analysis_summary(analysis), "result_meta": analysis.result_meta, "sources": [{"title": source.title, "url": source.url, "status": source.status, "content_hash": source.content_hash, "retrieved_at": source.retrieved_at.isoformat() if source.retrieved_at else None} for source in analysis.sources], "claims": rows}, ensure_ascii=False, indent=2)
        return Response(body, media_type="application/json; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}.json"'})
    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["claim", "normalized_claim", "status", "reasoning", "assessor", "uncertainty", "citations", "evidence"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"claim": row["claim"], "normalized_claim": row["normalized_claim"], "status": row["status"], "reasoning": row["reasoning"], "assessor": row["assessor"], "uncertainty": row["uncertainty"], "citations": " | ".join(item["url"] or item["raw"] for item in row["citations"]), "evidence": " | ".join(item["text"] for item in row["evidence"])})
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})
    if format == "markdown":
        lines = [f"# Verification report: {analysis.title}", "", f"- Created: {analysis.created_at.isoformat()}", f"- Mode: {analysis.mode}", f"- Status: {analysis.status}", "", "> Evidence-support assessment is not a guarantee of objective truth. A source can linguistically support an inaccurate or outdated claim.", ""]
        for row in rows:
            lines.extend([f"## {row['status'].replace('_', ' ').title()}", "", f"> {row['claim']}", "", row["reasoning"], ""])
            for item in row["citations"]:
                lines.append(f"- Citation: {item['raw']} ({item['resolution_status']})" + (f" — {item['url']}" if item["url"] else ""))
            for item in row["evidence"]:
                source = item["source_url"] or item["source_title"] or "source"
                lines.extend([f"- Evidence from [{item['source_title']}]({source})" + (f", page {item['page']}" if item["page"] else "") + f": “{item['text']}”"])
            for item in row["reviews"]:
                lines.append(f"- Human review by {item['reviewer']}: {item['decision']} — {item['notes']}")
            lines.append("")
        return Response("\n".join(lines), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}.md"'})
    sections = [f"<h1>{html.escape(analysis.title)}</h1><p><strong>Evidence support is not guaranteed factual truth.</strong></p>"]
    for row in rows:
        sections.append(f"<article><h2>{html.escape(row['status'].replace('_', ' ').title())}</h2><blockquote>{html.escape(row['claim'])}</blockquote><p>{html.escape(row['reasoning'])}</p>")
        for item in row["evidence"]:
            url = html.escape(item["source_url"] or "", quote=True)
            link = f'<a href="{url}">{html.escape(item["source_title"] or "Source")}</a>' if url.startswith(("http://", "https://")) else html.escape(item["source_title"] or "Source")
            sections.append(f"<p><strong>Retrieved evidence — {link}:</strong> {html.escape(item['text'])}</p>")
        sections.append("</article>")
    body = "<!doctype html><meta charset='utf-8'><title>Verification report</title><main>" + "".join(sections) + "</main>"
    return Response(body, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}.html"'})


def _secret_env(provider: str) -> str | None:
    return {"openai": os.getenv("OPENAI_API_KEY"), "anthropic": os.getenv("ANTHROPIC_API_KEY"), "openrouter": os.getenv("OPENROUTER_API_KEY"), "custom": os.getenv("CUSTOM_AI_API_KEY")}.get(provider)


def _validate_provider_endpoint(payload: ProviderConfigInput) -> None:
    if not payload.base_url:
        return
    parsed = urlsplit(payload.base_url)
    if parsed.username or parsed.password:
        raise HTTPException(400, "Provider base URLs must not embed credentials.")
    if config.api_tokens:
        if payload.provider in {"ollama", "lm_studio"}:
            raise HTTPException(400, "Multi-user mode blocks user-supplied local-model endpoints; configure an administrator-managed provider endpoint instead.")
        if parsed.scheme != "https":
            raise HTTPException(400, "Multi-user deployments require HTTPS provider endpoints.")
        try:
            from app.security.url_fetch import validate_public_url
            validate_public_url(payload.base_url)
        except ValueError as exc:
            raise HTTPException(400, f"Provider URL rejected: {exc}") from exc


@router.get("/providers")
def list_providers() -> dict:
    """Static, non-secret provider presets used by the easy-connect picker."""
    return {"providers": provider_catalog()}


@router.get("/settings/provider")
def get_provider_settings(request: Request, session: Session = Depends(get_db)) -> dict:
    owner = _owner(request)
    saved = session.get(ProviderSetting, owner)
    if not saved:
        return {"provider": "local", "base_url": None, "model": None, "has_api_key": False, "secret_storage": "none", "temperature": 0, "max_output_tokens": 8192, "timeout_seconds": 30, "retries": 2, "analysis_token_budget": 10000, "daily_token_budget": 50000}
    has_env = bool(_secret_env(saved.provider))
    has_key = has_env or bool(runtime_secrets.get(owner)) or bool(saved.encrypted_api_key and decrypt_secret(saved.encrypted_api_key))
    storage = "environment" if has_env else ("encrypted" if saved.encrypted_api_key and config.encryption_key else ("session_only" if runtime_secrets.get(owner) else "none"))
    usage = session.scalar(select(ProviderUsage).where(ProviderUsage.owner_id == owner, ProviderUsage.usage_date == datetime.now(UTC).date().isoformat()))
    return {"provider": saved.provider, "base_url": saved.base_url, "model": saved.model, "has_api_key": has_key, "secret_storage": storage, "temperature": saved.temperature, "max_output_tokens": saved.max_output_tokens, "timeout_seconds": saved.timeout_seconds, "retries": saved.retries, "analysis_token_budget": saved.analysis_token_budget, "daily_token_budget": saved.daily_token_budget, "daily_usage_estimate": usage.estimated_tokens if usage else 0, "daily_requests": usage.request_count if usage else 0, "remaining_daily_tokens": remaining_daily_tokens(session, owner, saved.daily_token_budget)}


@router.put("/settings/provider")
def save_provider_settings(payload: ProviderConfigInput, request: Request, session: Session = Depends(get_db)) -> dict:
    _validate_provider_endpoint(payload)
    owner = _owner(request)
    setting = session.get(ProviderSetting, owner)
    previous_provider = setting.provider if setting else None
    if not setting:
        setting = ProviderSetting(owner_id=owner)
        session.add(setting)
    if previous_provider is not None and previous_provider != payload.provider:
        # Never reuse a credential entered for a different provider.
        setting.encrypted_api_key = None
        runtime_secrets.pop(owner, None)
    setting.provider = payload.provider
    setting.base_url = payload.base_url
    setting.model = payload.model
    setting.temperature = payload.temperature
    setting.max_output_tokens = payload.max_output_tokens
    setting.timeout_seconds = payload.timeout_seconds
    setting.retries = payload.retries
    setting.analysis_token_budget = payload.analysis_token_budget
    setting.daily_token_budget = payload.daily_token_budget
    if payload.clear_api_key:
        setting.encrypted_api_key = None
        runtime_secrets.pop(owner, None)
    elif payload.api_key:
        encrypted = encrypt_secret(payload.api_key)
        setting.encrypted_api_key = encrypted
        if encrypted:
            runtime_secrets.pop(owner, None)
        else:
            runtime_secrets[owner] = payload.api_key
    session.commit()
    return get_provider_settings(request, session)


@router.post("/settings/provider/test")
def provider_test(payload: ProviderConfigInput, request: Request, session: Session = Depends(get_db)) -> dict:
    _validate_provider_endpoint(payload)
    provider = provider_config_from_payload(payload)
    if not provider.api_key:
        configured = provider_from_record(session, _owner(request))
        if configured.provider == payload.provider and configured.api_key:
            provider = replace(provider, api_key=configured.api_key)
        elif _secret_env(payload.provider):
            provider = replace(provider, api_key=_secret_env(payload.provider))
    try:
        result = test_provider(provider)
    except Exception as exc:
        from app.providers.base import ProviderError
        if isinstance(exc, ProviderError):
            raise HTTPException(400, str(exc)) from exc
        logger.exception("provider.test_failed", extra={"provider": payload.provider, "error_type": type(exc).__name__})
        raise HTTPException(502, "Provider connection test failed. Details were withheld from the response.") from exc
    return result


@router.get("/models/status")
def models_status() -> dict:
    from app.services.nlp import model_status
    return model_status()
