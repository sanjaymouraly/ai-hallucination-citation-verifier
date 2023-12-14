from __future__ import annotations

import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Analysis
from app.services.analysis import process_analysis

logger = logging.getLogger("verity.worker")


class AnalysisWorker:
    def __init__(self, session_factory: sessionmaker, poll_interval: float = 0.5):
        self.session_factory = session_factory
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="verity-analysis-worker", daemon=True)
        self._thread.start()
        logger.info("analysis worker started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("analysis worker stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            worked = False
            try:
                with self.session_factory() as session:
                    job = session.scalar(select(Analysis).where(Analysis.status == "queued").order_by(Analysis.created_at).limit(1))
                    if job:
                        worked = True
                        process_analysis(session, job.id)
            except Exception:
                logger.exception("worker loop failure")
            if not worked:
                self._stop.wait(self.poll_interval)
