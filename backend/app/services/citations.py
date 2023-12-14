from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class CitationMention:
    raw: str
    url: str | None
    kind: str
    start_char: int
    end_char: int
    external_id: str | None = None


def normalize_url(url: str) -> str:
    value = url.strip().rstrip(".,;:!?)\"]}")
    if value.lower().startswith("doi:"):
        value = "https://doi.org/" + value[4:].strip()
    if value.lower().startswith("10.") and "/" in value:
        value = "https://doi.org/" + value
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower() or "https"
        host = (parsed.hostname or "").lower()
        port = parsed.port
        netloc = host + (f":{port}" if port and port not in (80 if scheme == "http" else 443,) else "")
        if parsed.username or parsed.password:
            return value
        path = parsed.path.rstrip("/") or "/"
        return urlunsplit((scheme, netloc, path, parsed.query, ""))
    except ValueError:
        return value


def _references(text: str) -> tuple[dict[str, str], int | None]:
    heading = re.search(r"(?im)^\s*(?:references|bibliography|works cited)\s*:?[ \t]*$", text)
    if not heading:
        return {}, None
    found: dict[str, str] = {}
    for line in text[heading.end():].splitlines():
        m = re.match(r"\s*(?:\[(\d+)\]|\[(\^[^\]]+)\]|([^\n]{2,100}?,\s*\d{4}[a-z]?))\s*[.):]?\s*(.+)$", line)
        if not m:
            continue
        key = m.group(1) or m.group(2) or m.group(3)
        body = m.group(4)
        url_match = re.search(r"https?://[^\s)\]>]+|(?:doi:\s*)?10\.\d{4,9}/[^\s)\]>]+", body, re.IGNORECASE)
        if url_match:
            found[key.strip().lower()] = normalize_url(url_match.group(0))
    return found, heading.start()


def parse_citations(text: str) -> list[CitationMention]:
    refs, reference_start = _references(text)
    mentions: list[CitationMention] = []
    occupied: list[tuple[int, int]] = []

    def add(start: int, end: int, raw: str, url: str | None, kind: str, external_id: str | None = None) -> None:
        if any(start < old_end and end > old_start for old_start, old_end in occupied):
            return
        mentions.append(CitationMention(raw[:1000], url, kind, start, end, external_id))
        occupied.append((start, end))

    # Markdown links carry the actual URL, regardless of display label.
    for match in re.finditer(r"\[([^\]]{1,300})\]\((https?://[^\s)]+|doi:[^)]+)\)", text, flags=re.IGNORECASE):
        add(match.start(), match.end(), match.group(0), normalize_url(match.group(2)), "markdown_link")
    # Bare HTTP(S) URLs and DOI references.
    for match in re.finditer(r"https?://[^\s<>\]\)]+", text, flags=re.IGNORECASE):
        url = normalize_url(match.group(0))
        add(match.start(), match.end(), match.group(0), url, "url")
    for match in re.finditer(r"(?<![\w/])(?:doi:\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.IGNORECASE):
        add(match.start(), match.end(), match.group(0), normalize_url(match.group(1)), "doi")
    # Explicit local RAG identifiers such as [S1] or [source:S1].
    for match in re.finditer(r"\[(?:source:)?(S\d{1,5})\]", text, flags=re.IGNORECASE):
        add(match.start(), match.end(), match.group(0), None, "source_id", match.group(1).upper())
    # Numeric and footnote markers resolve only through a matching bibliography entry.
    for match in re.finditer(r"\[(\d{1,4}|\^[^\]]+)\]", text):
        key = match.group(1).lower()
        reference_url = refs.get(key)
        # Do not create a citation from markers inside the bibliography itself.
        if reference_start is not None and match.start() >= reference_start:
            continue
        add(match.start(), match.end(), match.group(0), reference_url, "numbered_reference" if reference_url else "unresolved_reference")
    # Author-year references are only linked when a bibliography entry matches exactly.
    for match in re.finditer(r"\(([A-Z][A-Za-z'’.-]+(?:\s+et\s+al\.)?,\s*\d{4}[a-z]?)\)", text):
        key = match.group(1).lower()
        reference_url = refs.get(key)
        if reference_url and (reference_start is None or match.start() < reference_start):
            add(match.start(), match.end(), match.group(0), reference_url, "named_reference")
    mentions.sort(key=lambda item: item.start_char)
    return mentions
