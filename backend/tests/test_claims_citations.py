from __future__ import annotations

from app.services.citations import parse_citations
from app.services.claims import extract_claims


def test_extracts_compound_claims_with_exact_source_offsets():
    text = "Company A increased revenue by 25% in 2024 and opened 12 new offices."
    claims = extract_claims(text)
    assert len(claims) == 2
    assert [claim.text for claim in claims] == ["Company A increased revenue by 25% in 2024", "opened 12 new offices."]
    for claim in claims:
        assert text[claim.start_char : claim.end_char] == claim.text
    assert claims[1].normalized_text == "Company A opened 12 new offices."


def test_does_not_split_decimal_values_and_preserves_multiline_locations():
    text = "The index rose to 12.5 points in 2024.\n- The team hired 15 people."
    claims = extract_claims(text)
    assert len(claims) == 2
    assert "12.5" in claims[0].text
    assert claims[1].text == "The team hired 15 people."
    assert text[claims[1].start_char : claims[1].end_char] == claims[1].text


def test_distinguishes_question_instruction_opinion_from_facts():
    text = "Why did the company move?\nPlease summarize the report.\nIn my opinion, this is the best design.\nThe company opened a factory in 2020."
    claims = extract_claims(text)
    assert [claim.kind for claim in claims] == ["not_factual", "not_factual", "not_factual", "factual"]


def test_reference_section_is_not_extracted_as_claims():
    text = "The report found a 12% change [1].\n\nReferences\n[1] Example Institute. Study results. https://example.org/study"
    claims = extract_claims(text)
    assert len(claims) == 1
    assert claims[0].text.startswith("The report found")


def test_markdown_bare_doi_numbered_and_source_id_citations():
    text = "The paper reports 12 cases [1]. The supplement is [PDF](https://example.org/supplement.pdf). DOI: 10.1234/abcd.5678 [S2].\n\nReferences\n[1] https://example.org/paper"
    mentions = parse_citations(text)
    by_kind = {item.kind: item for item in mentions}
    assert by_kind["numbered_reference"].url == "https://example.org/paper"
    assert any(item.kind == "markdown_link" and item.url == "https://example.org/supplement.pdf" for item in mentions)
    assert any(item.kind == "doi" and item.url == "https://doi.org/10.1234/abcd.5678" for item in mentions)
    assert any(item.kind == "source_id" and item.external_id == "S2" for item in mentions)


def test_unresolved_numeric_reference_is_not_invented():
    mentions = parse_citations("The report showed a 9% increase [8].")
    assert len(mentions) == 1
    assert mentions[0].kind == "unresolved_reference"
    assert mentions[0].url is None


def test_named_author_year_reference_resolves_only_when_in_bibliography():
    text = "A result was previously reported (Nguyen et al., 2022).\n\nReferences\nNguyen et al., 2022. Results. https://example.org/nguyen"
    mention = next(item for item in parse_citations(text) if item.kind == "named_reference")
    assert mention.url == "https://example.org/nguyen"
