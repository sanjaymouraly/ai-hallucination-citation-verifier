from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import config
from app.main import create_app


def test_shared_tokens_are_required_and_isolate_workspace_data(tmp_path):
    previous = config.api_tokens_raw
    object.__setattr__(config, "api_tokens_raw", "alice=" + "a" * 40 + ",bob=" + "b" * 40)
    app = create_app(f"sqlite:///{tmp_path / 'owners.db'}", run_worker=False)
    try:
        with TestClient(app) as client:
            assert client.get("/api/auth/status").json()["required"] is True
            assert client.get("/api/dashboard").status_code == 401
            alice_headers = {"Authorization": "Bearer " + "a" * 40}
            bob_headers = {"Authorization": "Bearer " + "b" * 40}
            created = client.post("/api/analyses", headers=alice_headers, json={"text": "The bridge opened in 2020."})
            assert created.status_code == 202
            analysis_id = created.json()["id"]
            assert client.get(f"/api/analyses/{analysis_id}", headers=bob_headers).status_code == 404
            assert client.get("/api/dashboard", headers=bob_headers).json()["total_analyses"] == 0
            assert client.get("/api/dashboard", headers=alice_headers).json()["total_analyses"] == 1
    finally:
        app.state.engine.dispose()
        object.__setattr__(config, "api_tokens_raw", previous)
