from __future__ import annotations

import json
from pathlib import Path

from app.services.claims import extract_claims
from app.services.evidence import _rule_assessment
from app.services.retrieval import rank_passages

ROOT = Path(__file__).resolve().parents[2]


def test_statuses_keep_missing_and_unavailable_distinct():
    missing = _rule_assessment("Company opened a site.", [], False, False, "citation_audit")
    unavailable = _rule_assessment("Company opened a site.", [], True, True, "citation_audit")
    insufficient = _rule_assessment("Company opened a site.", [], True, False, "citation_audit")
    assert missing.status == "citation_missing"
    assert unavailable.status == "source_unavailable"
    assert insufficient.status == "insufficient_evidence"
    assert "not evidence" in unavailable.reasoning.lower()


def test_exact_numeric_support_and_numerical_conflict():
    supported = _rule_assessment("Aster reported $42 million in 2024.", rank_passages("Aster reported $42 million in 2024.", [("S1", "Report", None, "Aster reported $42 million in 2024.")]), True, False, "citation_audit")
    contradicted = _rule_assessment("Aster reported $42 million in 2024.", rank_passages("Aster reported $42 million in 2024.", [("S1", "Report", None, "Aster reported $31 million in 2024.")]), True, False, "citation_audit")
    assert supported.status == "supported"
    assert contradicted.status == "contradicted"


def test_missing_numerical_detail_is_partial_not_contradicted():
    claim = "Aster Labs revenue rose by 25% to $50 million in 2024."
    evidence = "Aster Labs revenue rose by 25% in 2024."
    result = _rule_assessment(claim, rank_passages(claim, [("S1", "Report", None, evidence)]), True, False, "citation_audit")
    assert result.status == "partially_supported"


def test_absence_of_a_mention_is_not_mislabeled_as_a_contradiction():
    claim = "Acme Robotics launched its first lunar research station in 2025."
    evidence = "Acme Robotics announced an investment in laboratory automation. The release contains no information about a lunar research station."
    result = _rule_assessment(claim, rank_passages(claim, [("S1", "Release", None, evidence)]), True, False, "citation_audit")
    assert result.status == "needs_human_review"
    assert result.metadata["absence_of_evidence"] is True
    assert "absence of coverage is not a contradiction" in result.reasoning.lower()


def test_wrong_year_and_quotation_route_to_human_review():
    date = _rule_assessment("As of 2025, Northstar chief executive is Mara Lee.", rank_passages("Northstar chief executive is Mara Lee", [("S1", "Report", None, "As of 2017, Northstar chief executive was Mara Lee.")]), True, False, "citation_audit")
    quote_claim = 'The mayor said, "we will close the harbor tonight".'
    quote = _rule_assessment(quote_claim, rank_passages(quote_claim, [("S1", "Report", None, "Mayor Chen said crews would review harbor operations tomorrow.")]), True, False, "citation_audit")
    assert date.status == "needs_human_review"
    assert quote.status == "needs_human_review"


def test_local_evaluation_dataset_has_32_cases_and_reproduces_expected_labels():
    cases = json.loads((ROOT / "tests/evaluation/cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 30
    for case in cases:
        if case.get("kind") == "not_factual":
            candidates = extract_claims(case["claim"])
            prediction = "not_applicable" if candidates and candidates[0].kind == "not_factual" else "needs_human_review"
        else:
            passages = rank_passages(case["claim"], [(case["id"], "Fixture", None, case["passage"])], top_k=3) if case.get("passage") else []
            passages = [item for item in passages if item.score >= 0.025]
            prediction = _rule_assessment(case["claim"], passages, case.get("has_citation", True), case.get("source_unavailable", False), "citation_audit").status
        assert prediction == case["expected"], f"{case['id']}: expected {case['expected']}, got {prediction}"
