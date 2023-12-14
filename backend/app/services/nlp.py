"""Opt-in local NLP model status. Models are not downloaded unless configured explicitly."""

from __future__ import annotations

from app.core.config import config
from app.services.nli import nli_status


def model_status() -> dict:
    if not config.enable_local_models:
        return {"enabled": False, "embedding_model": None, "nli_model": None, "mode": "deterministic_fallback", "message": "Optional local NLP models are disabled. Retrieval and assessment use transparent deterministic rules; these are not semantic NLI."}
    try:
        import sentence_transformers  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return {"enabled": True, "available": False, "embedding_model": config.embedding_model, "nli_model": config.nli_model, "mode": "deterministic_fallback", "message": "Model mode was requested, but sentence-transformers/transformers are not installed. Install the local-models extra and fetch model weights, or disable model mode."}
    nli = nli_status()
    return {"enabled": True, "available": True, "embedding_model": config.embedding_model, "nli_model": config.nli_model, "mode": "optional_embeddings_and_nli_with_rules_fallback", "message": "Local sentence-transformer embeddings rank passages; the local NLI model may assess clear entailment/contradiction when its weights are available. Neither output is a calibrated truth probability. " + nli["message"], "allow_downloads": config.allow_model_downloads}
