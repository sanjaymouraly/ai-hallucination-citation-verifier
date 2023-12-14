"""Exercise the API and ORM against an explicitly supplied disposable database.

The script is used by CI's PostgreSQL job and may also be run locally against a
throwaway SQLite or PostgreSQL database. It creates and then deletes one sample
analysis; it never prints the connection URL or request content.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4


def main() -> None:
    database_url = os.environ.get("VERITY_SMOKE_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Set VERITY_SMOKE_DATABASE_URL to a disposable database before running this smoke check.")

    # Ensure both the module-level application and the tested application use
    # the explicitly selected database, never another configured/default DB.
    os.environ["DATABASE_URL"] = database_url
    os.environ["WORKER_ENABLED"] = "false"
    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))

    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services.analysis import process_analysis

    application = create_app(database_url, run_worker=False)
    token = os.environ.get("VERITY_SMOKE_BEARER_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    analysis_id: str | None = None

    with TestClient(application) as client:
        health = client.get("/health")
        if health.status_code != 200 or health.json().get("status") != "ok":
            raise RuntimeError(f"Health check failed with HTTP {health.status_code}.")

        title = f"Database smoke check {uuid4()}"
        queued = client.post(
            "/api/analyses",
            headers=headers,
            json={
                "title": title,
                "text": "The organization opened 8 clinics in 2024 [S1].",
                "sources": [
                    {
                        "id": "S1",
                        "title": "Smoke-test source",
                        "content": "The organization opened 8 clinics in 2024.",
                    }
                ],
            },
        )
        if queued.status_code != 202:
            raise RuntimeError(f"Could not queue smoke analysis (HTTP {queued.status_code}).")
        analysis_id = queued.json()["id"]

        try:
            with application.state.session_factory() as session:
                process_analysis(session, analysis_id)

            result = client.get(f"/api/analyses/{analysis_id}", headers=headers)
            if result.status_code != 200:
                raise RuntimeError(f"Could not reload smoke analysis (HTTP {result.status_code}).")
            report = result.json()
            if report.get("status") != "completed" or not report.get("claims"):
                raise RuntimeError("Smoke analysis did not persist a completed claim-level report.")

            deleted = client.delete(f"/api/analyses/{analysis_id}", headers=headers)
            if deleted.status_code != 204:
                raise RuntimeError(f"Could not clean up smoke analysis (HTTP {deleted.status_code}).")
            analysis_id = None
        finally:
            if analysis_id:
                # Keep disposable CI databases tidy even if assessment assertions fail.
                client.delete(f"/api/analyses/{analysis_id}", headers=headers)

    print(f"Database/API smoke check passed ({application.state.engine.dialect.name}).")


if __name__ == "__main__":
    main()
