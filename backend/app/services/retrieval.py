from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import config

_STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "was", "were", "with", "which", "who", "has", "have", "had", "its", "our", "your", "according", "reported", "says", "said", "claim", "claims"}


@dataclass(frozen=True)
class Passage:
    source_id: str
    source_title: str
    source_url: str | None
    text: str
    start_char: int
    end_char: int
    page: int | None
    section: str | None
    score: float
    fingerprint: str


_embedding_model: Any = None


def terms(text: str) -> list[str]:
    return [word.lower() for word in re.findall(r"[\w%$€£]+", text, flags=re.UNICODE) if len(word) > 1 and word.lower() not in _STOP]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def split_passages(source_id: str, title: str, url: str | None, text: str, chunk_chars: int = 950, overlap: int = 100) -> list[Passage]:
    passages: list[Passage] = []
    if not text:
        return passages
    # Paragraph windows keep traceable offsets and normally preserve sentence context.
    blocks = list(re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|$)", text, flags=re.DOTALL))
    if not blocks:
        blocks = [re.match(r"(?s).+", text)]  # type: ignore[list-item]
    for block in blocks:
        if block is None:
            continue
        start, end = block.span()
        cursor = start
        while cursor < end:
            stop = min(cursor + chunk_chars, end)
            if stop < end:
                boundary = text.rfind(" ", cursor + chunk_chars // 2, stop)
                if boundary > cursor:
                    stop = boundary
            passage_text = text[cursor:stop].strip()
            actual_start = cursor + len(text[cursor:stop]) - len(text[cursor:stop].lstrip())
            actual_end = actual_start + len(passage_text)
            if passage_text:
                page_match = re.search(r"\[Page\s+(\d+)\]", text[max(0, actual_start - 30):actual_start + 50], re.IGNORECASE)
                page = int(page_match.group(1)) if page_match else None
                passages.append(Passage(source_id, title, url, passage_text, actual_start, actual_end, page, None, 0.0, content_hash(passage_text)))
            if stop >= end:
                break
            cursor = max(cursor + 1, stop - overlap)
    return passages


def _embedding_scores(query: str, passages: list[Passage]) -> list[float] | None:
    if not config.enable_local_models:
        return None
    try:
        from sentence_transformers import SentenceTransformer, util
        global _embedding_model
        model = _embedding_model
        if model is None:
            model = SentenceTransformer(config.embedding_model, local_files_only=not config.allow_model_downloads)
            _embedding_model = model
        vectors = model.encode([query, *[passage.text for passage in passages]], convert_to_tensor=True, normalize_embeddings=True)
        values = util.cos_sim(vectors[0], vectors[1:])[0].tolist()
        return [max(0.0, float(value)) for value in values]
    except (ImportError, OSError, RuntimeError, ValueError):
        return None


def rank_passages(query: str, sources: list[tuple[str, str, str | None, str]], top_k: int = 5) -> list[Passage]:
    query_terms = set(terms(query))
    if not query_terms:
        return []
    candidates: list[Passage] = []
    for source_id, title, url, content in sources:
        candidates.extend(split_passages(source_id, title, url, content))
    if not candidates:
        return []
    embeddings = _embedding_scores(query, candidates)
    ranked: list[Passage] = []
    for index, passage in enumerate(candidates):
        passage_terms = set(terms(passage.text))
        overlap = len(query_terms & passage_terms)
        coverage = overlap / max(1, len(query_terms))
        precision = overlap / max(1, len(passage_terms))
        lexical = 0.78 * coverage + 0.22 * precision
        score = (0.65 * lexical + 0.35 * embeddings[index]) if embeddings is not None else lexical
        ranked.append(Passage(passage.source_id, passage.source_title, passage.source_url, passage.text, passage.start_char, passage.end_char, passage.page, passage.section, float(score), passage.fingerprint))
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]
