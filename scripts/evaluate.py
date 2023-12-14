from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.claims import extract_claims  # noqa: E402
from app.services.evidence import _rule_assessment  # noqa: E402
from app.services.retrieval import rank_passages  # noqa: E402


def _metrics(cases: list[dict], predictions: dict[str, str]) -> dict:
    labels = sorted({case["expected"] for case in cases} | set(predictions.values()))
    confusion = {label: Counter() for label in labels}
    for case in cases:
        confusion[case["expected"]][predictions[case["id"]]] += 1
    per_class = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[actual][label] for actual in labels if actual != label)
        fn = sum(confusion[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    accuracy = sum(predictions[case["id"]] == case["expected"] for case in cases) / max(1, len(cases))
    return {"accuracy": accuracy, "macro_f1": sum(item["f1"] for item in per_class.values()) / max(1, len(per_class)), "per_class": per_class, "confusion": confusion}


def evaluate() -> tuple[dict, list[dict]]:
    cases = json.loads((ROOT / "tests/evaluation/cases.json").read_text(encoding="utf-8"))
    predictions: dict[str, str] = {}
    details: list[dict] = []
    for case in cases:
        if case.get("kind") == "not_factual":
            candidates = extract_claims(case["claim"])
            prediction = "not_applicable" if candidates and candidates[0].kind == "not_factual" else "needs_human_review"
        else:
            passages = []
            if case.get("passage"):
                ranked = rank_passages(case["claim"], [(case["id"], "Evaluation source", None, case["passage"])], top_k=3)
                passages = [item for item in ranked if item.score >= 0.025]
            assessment = _rule_assessment(case["claim"], passages, bool(case.get("has_citation", True)), bool(case.get("source_unavailable", False)), "citation_audit")
            prediction = assessment.status
        predictions[case["id"]] = prediction
        details.append({**case, "predicted": prediction, "pass": prediction == case["expected"]})
    return _metrics(cases, predictions), details


def write_report(metrics: dict, details: list[dict]) -> None:
    lines = [
        "# Deterministic fixture evaluation",
        "",
        f"Run date: 2026-10-16 · Examples: {len(details)}",
        "",
        "This small, hand-authored fixture set is a regression aid, not an external benchmark or a claim of real-world accuracy. The labels are scenario expectations and the rule-based output is intentionally conservative. It measures only these local examples.",
        "",
        f"- Accuracy: **{metrics['accuracy']:.3f}**",
        f"- Macro F1: **{metrics['macro_f1']:.3f}**",
        "",
        "## Per-status metrics",
        "",
        "| Status | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, values in metrics["per_class"].items():
        lines.append(f"| `{label}` | {values['precision']:.3f} | {values['recall']:.3f} | {values['f1']:.3f} | {values['support']} |")
    lines.extend(["", "## Cases requiring attention", ""])
    failures = [case for case in details if not case["pass"]]
    if failures:
        for case in failures:
            lines.append(f"- **{case['id']}** ({case['category']}): expected `{case['expected']}`, got `{case['predicted']}` — {case['claim']}")
    else:
        lines.append("All fixture expectations matched in this run.")
    lines.extend(["", "## Interpretation", "", "These results do not estimate the probability that any claim is true. Retrieval and labels remain sensitive to source quality, paraphrase, context, chronology, qualifiers, and domain-specific language. Run `python scripts/evaluate.py` after changes to reproduce this local check.", ""])
    (ROOT / "docs/evaluation-results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    metrics, details = evaluate()
    write_report(metrics, details)
    print(f"Examples={len(details)} accuracy={metrics['accuracy']:.3f} macro_f1={metrics['macro_f1']:.3f}")
    for case in details:
        if not case["pass"]:
            print(f"FAIL {case['id']}: expected={case['expected']} predicted={case['predicted']} ({case['category']})")
    print(f"Report: {ROOT / 'docs/evaluation-results.md'}")
    return 1 if any(not case["pass"] for case in details) else 0


if __name__ == "__main__":
    raise SystemExit(main())
