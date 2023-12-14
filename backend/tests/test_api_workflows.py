from __future__ import annotations

import csv
import io

from conftest import create_and_process
from fastapi.testclient import TestClient

from app.core.config import config
from app.models import Analysis


def test_full_local_pipeline_review_history_and_exports(client: TestClient, app):
    text = "Acme Robotics opened 12 offices in 2024 and increased revenue by 25% compared with 2023 [S1].\nThe company reported $45 million in revenue in 2024 [S2].\nAcme Robotics launched a lunar research station in 2025 [S3].\nThe company claims it has won every award."
    sources = [
        {"id": "S1", "title": "Annual update", "content": "Acme Robotics opened 12 offices in 2024. Revenue rose by 25% compared with 2023."},
        {"id": "S2", "title": "Revenue release", "content": "Acme Robotics reported revenue of $45 million in 2024."},
        {"id": "S3", "title": "Unrelated release", "content": "Acme Robotics announced a laboratory investment and expanded its engineering team."},
    ]
    result = create_and_process(client, app, text, sources, title="Local end-to-end")
    assert result["status"] == "completed"
    assert len(result["claims"]) >= 4
    assert result["claims"][0]["text"] == "Acme Robotics opened 12 offices in 2024"
    assert result["claims"][0]["citations"][0]["resolution_status"] == "resolved"
    assert result["claims"][0]["status"] == "supported"
    assert result["claims"][0]["evidence"][0]["text"] == sources[0]["content"]
    assert result["claims"][2]["status"] == "supported"
    assert result["claims"][3]["status"] in {"needs_human_review", "insufficient_evidence"}
    assert result["result_meta"]["source_hashes"]

    claim_id = result["claims"][3]["id"]
    review = client.post(f"/api/claims/{claim_id}/reviews", json={"decision": "needs_more_evidence", "notes": "This source is about investments, not a station.", "reviewer": "QA"})
    assert review.status_code == 201
    updated = client.get(f"/api/analyses/{result['id']}").json()
    assert updated["claims"][3]["reviews"][0]["decision"] == "needs_more_evidence"
    queue = client.get("/api/reviews?status=all").json()
    assert any(item["id"] == claim_id and item["reviewed"] for item in queue["items"])

    json_export = client.get(f"/api/analyses/{result['id']}/export?format=json")
    assert json_export.status_code == 200 and "source_hash" in json_export.text
    csv_export = client.get(f"/api/analyses/{result['id']}/export?format=csv")
    assert csv_export.status_code == 200
    parsed_csv = list(csv.DictReader(io.StringIO(csv_export.text)))
    assert len(parsed_csv) == len(result["claims"])
    markdown_export = client.get(f"/api/analyses/{result['id']}/export?format=markdown")
    assert "not a guarantee of objective truth" in markdown_export.text.lower()
    html_export = client.get(f"/api/analyses/{result['id']}/export?format=html")
    assert html_export.status_code == 200

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["total_analyses"] == 1
    assert dashboard["total_claims"] == len(result["claims"])
    # New sessions/reloads see durable saved rows.
    with app.state.session_factory() as session:
        saved = session.get(Analysis, result["id"])
        assert saved is not None and saved.status == "completed"


def test_citation_missing_unavailable_and_irrelevant_source_are_distinct(client: TestClient, app):
    result = create_and_process(client, app, "The university has 14 libraries.\nThe museum opened a new gallery in 2020 [S1].\nThe station moved 200 people in 2021 [8].", [{"id": "S1", "title": "Unrelated", "content": "The source discusses modern garden design and native plants."}])
    statuses = [claim["status"] for claim in result["claims"]]
    assert statuses[0] == "citation_missing"
    assert statuses[1] in {"insufficient_evidence", "needs_human_review"}
    assert statuses[2] == "source_unavailable"


def test_batch_compare_and_delete(client: TestClient, app):
    batch = client.post("/api/batches", json={"items": [{"title": "Version A", "text": "Revenue was $20 million in 2024 [S1].", "sources": [{"id": "S1", "title": "Report", "content": "Revenue was $20 million in 2024."}]}, {"title": "Version B", "text": "Revenue was $30 million in 2024 [S1].", "sources": [{"id": "S1", "title": "Report", "content": "Revenue was $20 million in 2024."}]}]})
    assert batch.status_code == 202
    batch_id = batch.json()["batch_id"]
    ids = [item["id"] for item in batch.json()["items"]]
    with app.state.session_factory() as session:
        for analysis_id in ids:
            from app.services.analysis import process_analysis
            process_analysis(session, analysis_id)
    report = client.get(f"/api/batches/{batch_id}").json()
    assert report["complete"] is True and report["counts"]["completed"] == 2
    comparison = client.post("/api/compare", json={"left_id": ids[0], "right_id": ids[1]}).json()
    assert comparison["changes"]
    assert comparison["changes"][0]["old_status"] != comparison["changes"][0]["new_status"]
    assert client.delete(f"/api/analyses/{ids[0]}").status_code == 204
    assert client.get(f"/api/analyses/{ids[0]}").status_code == 404


def test_upload_flow_and_input_validation(client: TestClient):
    response = client.post("/api/analyses/upload", data={"title": "Uploaded report", "mode": "citation_audit", "sources_json": "[]"}, files={"input_file": ("answer.txt", b"The firm opened 3 offices in 2022.", "text/plain")})
    assert response.status_code == 202, response.text
    bad = client.post("/api/analyses/upload", data={"title": "Bad upload", "mode": "citation_audit"}, files={"input_file": ("payload.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 422
    invalid_url = client.post("/api/analyses", json={"text": "The claim is true.", "sources": [{"title": "Bad URL", "url": "javascript:alert(1)", "content": "Source text."}]})
    assert invalid_url.status_code == 422
    secret = "do-not-reflect-this-token"
    invalid = client.post("/api/analyses", json={"text": " ", "api_key": secret})
    assert invalid.status_code == 422 and secret not in invalid.text


def test_upload_enforces_aggregate_file_size_limit(client: TestClient):
    previous_limit = config.max_total_upload_bytes
    object.__setattr__(config, "max_total_upload_bytes", 5)
    try:
        response = client.post(
            "/api/analyses/upload",
            data={"text": "A project opened in 2024.", "sources_json": "[]"},
            files=[("evidence_files", ("one.txt", b"123", "text/plain")), ("evidence_files", ("two.txt", b"456", "text/plain"))],
        )
        assert response.status_code == 413
        assert "aggregate" in response.json()["detail"]
    finally:
        object.__setattr__(config, "max_total_upload_bytes", previous_limit)


def test_every_non_deterministic_provider_requires_per_job_consent(client: TestClient, app):
    saved = client.put("/api/settings/provider", json={"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "local-model"})
    assert saved.status_code == 200
    payload = {"text": "The report says the project opened in 2024.", "use_ai": True}
    denied = client.post("/api/analyses", json=payload)
    assert denied.status_code == 400 and "Confirm" in denied.json()["detail"]
    permitted = client.post("/api/analyses", json={**payload, "confirm_external_processing": True})
    assert permitted.status_code == 202
    analysis_id = permitted.json()["id"]
    from app.services.analysis import process_analysis
    with app.state.session_factory() as session:
        process_analysis(session, analysis_id)
    rerun_without_consent = client.post(f"/api/analyses/{analysis_id}/rerun")
    assert rerun_without_consent.status_code == 400
    rerun_confirmed = client.post(f"/api/analyses/{analysis_id}/rerun?confirm_external_processing=true")
    assert rerun_confirmed.status_code == 202


def test_html_report_escapes_user_content(client: TestClient, app):
    result = create_and_process(client, app, "The <script>alert('x')</script> company reported 5 sales in 2024.")
    report = client.get(f"/api/analyses/{result['id']}/export?format=html")
    assert "<script>" not in report.text
    assert "&lt;script&gt;" in report.text
