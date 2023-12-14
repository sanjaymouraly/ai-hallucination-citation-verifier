from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env from the backend or repo root without overriding real environment variables.

    Docker Compose injects these values itself; this keeps a plain `uvicorn` run
    consistent with the documented .env workflow.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parents[3] / ".env", here.parents[2] / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")
        return


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


_load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///../data/verity.db")
    worker_enabled: bool = os.getenv("WORKER_ENABLED", "true").lower() in {"1", "true", "yes"}
    encryption_key: str | None = os.getenv("APP_ENCRYPTION_KEY") or None
    cors_origins: tuple[str, ...] = tuple(_csv(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")))
    max_input_chars: int = int(os.getenv("MAX_INPUT_CHARS", "200000"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_total_upload_bytes: int = int(os.getenv("MAX_TOTAL_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    max_source_bytes: int = int(os.getenv("MAX_SOURCE_BYTES", str(5 * 1024 * 1024)))
    max_claims: int = int(os.getenv("MAX_CLAIMS", "120"))
    enable_local_models: bool = os.getenv("VERITY_ENABLE_LOCAL_MODELS", "false").lower() in {"1", "true", "yes"}
    allow_model_downloads: bool = os.getenv("VERITY_ALLOW_MODEL_DOWNLOADS", "false").lower() in {"1", "true", "yes"}
    embedding_model: str = os.getenv("VERITY_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    nli_model: str = os.getenv("VERITY_NLI_MODEL", "cross-encoder/nli-deberta-v3-base")
    api_tokens_raw: str = os.getenv("APP_API_TOKENS", "")

    @property
    def api_tokens(self) -> dict[str, str]:
        """Return {token: owner} from APP_API_TOKENS=reviewer=long-secret,..."""
        mapping: dict[str, str] = {}
        for item in _csv(self.api_tokens_raw):
            if "=" not in item:
                continue
            owner, token = item.split("=", 1)
            owner, token = owner.strip(), token.strip()
            if owner and token:
                mapping[token] = owner
        return mapping


config = AppConfig()


def ensure_data_dir() -> Path:
    path = Path(os.getenv("DATA_DIR", "../data")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
