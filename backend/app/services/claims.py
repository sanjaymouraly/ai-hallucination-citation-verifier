from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimCandidate:
    text: str
    normalized_text: str
    start_char: int
    end_char: int
    kind: str


_VERBS = {
    "is", "are", "was", "were", "has", "have", "had", "does", "did", "increased", "decreased", "rose", "fell", "grew", "declined", "opened", "closed", "added", "removed", "created", "launched", "acquired", "reported", "reached", "generated", "produced", "employs", "employed", "serves", "served", "published", "discovered", "found", "caused", "led", "contains", "contained", "includes", "included", "accounts", "accounted", "became", "won", "lost", "measures", "measured", "weighs", "weighed", "occurred", "began", "ended", "involved", "affects", "affected", "supports", "showed", "shows", "demonstrated", "indicates", "indicated", "uses", "used", "owns", "owned", "occupies", "covers", "covered", "isn't", "aren't", "wasn't", "weren't", "didn't", "doesn't", "hasn't", "haven't", "hadn't", "cannot", "can't", "will", "would", "can", "may", "must", "should", "remains", "remain", "stands", "stood", "ranks", "ranked", "built", "established", "founded", "operates", "operated", "sells", "sold", "imports", "exports", "lives", "lived", "exists", "occur", "averages", "averaged", "equals", "equaled", "outnumbered", "outnumbers", "not"
}


def _is_reference_tail(text: str, index: int) -> bool:
    tail = text[index:]
    first_lines = tail.splitlines()[:3]
    if re.match(r"(?is)^\s*(?:references|bibliography|works cited)\s*:?(?:\s|$)", "\n".join(first_lines)):
        return True
    return False


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Split on sentence punctuation and hard line boundaries, preserving offsets."""
    spans: list[tuple[int, int]] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "\r\n":
            end = i
            if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                i += 1
            if text[start:end].strip():
                spans.append((start, end))
            start = i + 1
            i += 1
            continue
        if ch in ".!?" and not (ch == "." and i > 0 and i + 1 < n and text[i - 1].isdigit() and text[i + 1].isdigit()):
            j = i + 1
            # Keep citation markers immediately after sentence punctuation with the sentence.
            while j < n and text[j].isspace() and text[j] not in "\r\n":
                j += 1
            while j < n and text[j] == "[":
                close = text.find("]", j + 1)
                if close < 0:
                    break
                j = close + 1
                if j < n and text[j] == "(":
                    close_paren = text.find(")", j + 1)
                    if close_paren < 0:
                        break
                    j = close_paren + 1
                while j < n and text[j].isspace() and text[j] not in "\r\n":
                    j += 1
            if j >= n or text[j].isupper() or text[j].isdigit() or text[j] in "“\"'":
                end = j if j < n and text[j] == "[" else i + 1
                # Include post-punctuation citation markers in the previous exact span.
                if j > i + 1:
                    end = j
                if text[start:end].strip():
                    spans.append((start, end))
                start = j
                i = j
                continue
        i += 1
    if text[start:n].strip():
        spans.append((start, n))
    return spans


def _trim_markdown_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    bullet = re.match(r"(?:[-*+]\s+|\d+[.)]\s+)", text[start:end])
    if bullet:
        start += bullet.end()
    return start, end


def _clean_claim(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\((?:https?://|mailto:)[^)]+\)", r"\1", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"\[(?:\d+|\^?[^\]]+)\]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\n\r-–—*#")


def _is_nonfactual(value: str) -> bool:
    cleaned = value.strip()
    low = cleaned.lower()
    if not cleaned:
        return True
    if "?" in cleaned or re.match(r"^(?:what|why|how|when|where|who|which|can you|could you|would you|please|explain|summarize|compare|list|write|calculate|tell me)\b", low):
        return True
    if re.match(r"^(?:i think|i believe|in my opinion|my view is|arguably|beautiful|wonderful|awful)\b", low):
        return True
    # Markdown headings and bare labels are not factual propositions.
    if re.match(r"^#{1,6}\s", cleaned) or (len(cleaned.split()) < 3 and not re.search(r"\d", cleaned)):
        return True
    return False


def _split_atomic(text: str, start: int, end: int) -> list[tuple[int, int, str | None]]:
    segment = text[start:end]
    matches = list(re.finditer(r"\s+and\s+", segment, flags=re.IGNORECASE))
    if not matches:
        return [(start, end, None)]
    cuts: list[tuple[int, int, str | None]] = []
    cursor = 0
    first_clause = ""
    subject = ""
    for match in matches:
        left = segment[cursor:match.start()].strip()
        right = segment[match.end():].lstrip()
        first_word = re.match(r"([A-Za-z]+)", right)
        if not first_word or first_word.group(1).lower() not in _VERBS:
            continue
        if not first_clause:
            first_clause = left
            # Infer a short subject for the normalized form only; source span stays exact.
            m = re.match(r"(.+?)\s+(?:" + "|".join(sorted(_VERBS, key=len, reverse=True)) + r")\b", left, flags=re.IGNORECASE)
            if m:
                subject = m.group(1).strip()
        absolute_start = start + cursor
        absolute_end = start + match.start()
        cuts.append((absolute_start, absolute_end, None))
        cursor = match.end()
    if not cuts:
        return [(start, end, None)]
    cuts.append((start + cursor, end, subject or None))
    # Each split fragment receives the inherited subject only in its normalized representation.
    return cuts


def extract_claims(text: str, max_claims: int = 120) -> list[ClaimCandidate]:
    results: list[ClaimCandidate] = []
    for raw_start, raw_end in _sentence_spans(text):
        if _is_reference_tail(text, raw_start):
            break
        start, end = _trim_markdown_span(text, raw_start, raw_end)
        if end <= start:
            continue
        for part_start, part_end, inherited_subject in _split_atomic(text, start, end):
            part_start, part_end = _trim_markdown_span(text, part_start, part_end)
            raw = text[part_start:part_end]
            normalized = _clean_claim(raw)
            if inherited_subject and normalized:
                normalized = f"{inherited_subject} {normalized}".strip()
            if not raw.strip() or not normalized:
                continue
            kind = "not_factual" if _is_nonfactual(normalized) else "factual"
            results.append(ClaimCandidate(raw, normalized, part_start, part_end, kind))
            if len(results) >= max_claims:
                return results
    return results
