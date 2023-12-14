from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.engine import Engine

# Import model declarations before metadata creation.
from app import models as _models  # noqa: F401
from app.api.routes import router
from app.core.config import config, ensure_data_dir
from app.database import Base, make_engine, make_session_factory
from app.security.auth import OwnerAuthMiddleware
from app.workers.worker import AnalysisWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(database_url: str | None = None, run_worker: bool | None = None, engine: Engine | None = None) -> FastAPI:
    db_url = database_url or config.database_url
    if db_url.startswith("sqlite"):
        ensure_data_dir()
    db_engine = engine or make_engine(db_url)
    Base.metadata.create_all(db_engine)
    factory = make_session_factory(db_engine)
    should_run_worker = config.worker_enabled if run_worker is None else run_worker
    worker = AnalysisWorker(factory) if should_run_worker else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if worker:
            # Requeue jobs that were interrupted by a process restart. Do not drop durable work.
            from datetime import UTC, datetime

            from app.models import Analysis
            with factory() as recovery_session:
                interrupted = list(recovery_session.scalars(select(Analysis).where(Analysis.status == "running")).all())
                for job in interrupted:
                    if job.cancel_requested:
                        job.status = "cancelled"
                        job.progress = 100
                    else:
                        job.status = "queued"
                        job.progress = 0
                    job.updated_at = datetime.now(UTC)
                recovery_session.commit()
            worker.start()
        yield
        if worker:
            worker.stop()
        db_engine.dispose()

    app = FastAPI(
        title="Verity — AI Evidence Support Checker",
        description="Evidence-support analysis for factual claims and their citations. A support assessment is not a guarantee of objective truth.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.engine = db_engine
    app.state.session_factory = factory
    app.state.worker = worker
    app.add_middleware(OwnerAuthMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        # Do not reflect submitted values: they may contain API keys or private source text.
        errors = [{"loc": error.get("loc", []), "msg": error.get("msg", "Invalid input"), "type": error.get("type", "value_error")} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/health", tags=["operations"])
    def health() -> dict:
        return {"status": "ok", "service": "verity-api", "version": "0.1.0"}

    app.include_router(router)
    return app


app = create_app()
