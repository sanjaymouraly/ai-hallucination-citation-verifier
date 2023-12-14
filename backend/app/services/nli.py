"""Optional, local-only NLI assessor. Model labels are read from model metadata; no truth probability is reported."""

from __future__ import annotations

from typing import Any

from app.core.config import config
from app.services.retrieval import Passage


class LocalNLI:
    def __init__(self) -> None:
        self.model: Any = None
        self.tokenizer: Any = None
        self.torch: Any = None
        self.labels: dict[int, str] = {}
        self.error: str | None = None

    def _load(self) -> bool:
        if self.model is not None:
            return True
        if self.error:
            return False
        if not config.enable_local_models:
            return False
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            opts = {"local_files_only": not config.allow_model_downloads}
            self.tokenizer = AutoTokenizer.from_pretrained(config.nli_model, **opts)
            self.model = AutoModelForSequenceClassification.from_pretrained(config.nli_model, **opts)
            self.model.eval()
            self.torch = torch
            mapping = self.model.config.id2label or {}
            self.labels = {int(index): str(label).lower() for index, label in mapping.items()}
            if not any(any(term in label for term in ("entail", "contrad", "neutral")) for label in self.labels.values()):
                self.error = "The selected NLI model does not expose recognizable entailment labels."
                self.model = None
                return False
            return True
        except Exception as exc:  # Model loading may fail without weights/network; fallback is explicit.
            self.error = f"Local NLI model unavailable ({type(exc).__name__})."
            self.model = None
            return False

    def classify(self, claim: str, passages: list[Passage]) -> dict[str, Any] | None:
        if not self._load():
            return None
        best_entail = 0.0
        best_contradiction = 0.0
        for passage in passages[:5]:
            premise = passage.text[:1800]
            inputs = self.tokenizer(premise, claim[:800], return_tensors="pt", truncation=True, max_length=512)
            with self.torch.no_grad():
                logits = self.model(**inputs).logits[0]
                scores = self.torch.softmax(logits, dim=-1).tolist()
            for index, label in self.labels.items():
                if index >= len(scores):
                    continue
                if "entail" in label:
                    best_entail = max(best_entail, float(scores[index]))
                elif "contrad" in label:
                    best_contradiction = max(best_contradiction, float(scores[index]))
        # These are conservative model decision thresholds, not calibrated probabilities.
        if best_entail >= 0.82 and best_entail > best_contradiction + 0.10:
            return {"status": "supported", "assessor": config.nli_model, "uncertainty": "moderate", "reasoning": "The optional local NLI model classified one or more retrieved passages as entailing the claim. Model outputs are not calibrated truth probabilities; inspect the original source and qualifications."}
        if best_contradiction >= 0.82 and best_contradiction > best_entail + 0.10:
            return {"status": "contradicted", "assessor": config.nli_model, "uncertainty": "moderate", "reasoning": "The optional local NLI model detected a possible contradiction between the claim and retrieved passage. Review source context before treating this as a factual contradiction."}
        return None


_local_nli = LocalNLI()


def nli_assess(claim: str, passages: list[Passage]) -> dict[str, Any] | None:
    return _local_nli.classify(claim, passages)


def nli_status() -> dict[str, Any]:
    if not config.enable_local_models:
        return {"enabled": False, "model": None, "loaded": False, "message": "Optional local NLI is disabled; deterministic rule-based assessment is used."}
    return {"enabled": True, "model": config.nli_model, "loaded": _local_nli.model is not None, "message": _local_nli.error or ("Weights are loaded on first use when available. NLI outputs are not calibrated truth probabilities." if _local_nli.model is None else "Local NLI model loaded; ambiguous cases still use rule-based fallback.")}
