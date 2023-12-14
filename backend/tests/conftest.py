from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.analysis import process_analysis


@pytest.fixture
def app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    application = create_app(f"sqlite:///{database_path}", run_worker=False)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def create_and_process(client: TestClient, app, text: str, sources: list[dict] | None = None, mode: str = "citation_audit", title: str = "Test analysis") -> dict:
    response = client.post("/api/analyses", json={"title": title, "text": text, "mode": mode, "sources": sources or []})
    assert response.status_code == 202, response.text
    analysis_id = response.json()["id"]
    with app.state.session_factory() as session:
        process_analysis(session, analysis_id)
    result = client.get(f"/api/analyses/{analysis_id}")
    assert result.status_code == 200, result.text
    return result.json()
