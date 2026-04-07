"""
Unit tests for query_engine/context.py.

These tests are pure in-memory — no database, no network.
"""
import uuid

import pytest

from app.query_engine.context import (
    assemble_context,
    count_tokens,
    extract_citations,
    format_context,
)
from app.retrieval.schemas import SearchResult

# ── Helpers ───────────────────────────────────────────────────────────────────

_DOMAIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_DOC_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _make_chunk(text: str, chunk_index: int = 0, title: str = "Test Doc") -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid4(),
        document_id=_DOC_ID,
        domain_id=_DOMAIN_ID,
        document_title=title,
        chunk_index=chunk_index,
        text=text,
        score=0.9,
    )


# ── count_tokens ──────────────────────────────────────────────────────────────

def test_count_tokens_returns_int():
    result = count_tokens("Hello, world!")
    assert isinstance(result, int)
    assert result > 0


def test_count_tokens_empty_string():
    assert count_tokens("") == 0


def test_count_tokens_longer_text_has_more_tokens():
    short = count_tokens("Hi")
    long = count_tokens("Hi " * 100)
    assert long > short


# ── format_context ────────────────────────────────────────────────────────────

def test_format_context_includes_source_labels():
    chunks = [
        _make_chunk("Paris is the capital.", title="Europe Guide"),
        _make_chunk("The Eiffel Tower is tall.", title="Paris Facts"),
    ]
    result = format_context(chunks)
    assert "[SOURCE 1: Europe Guide]" in result
    assert "[SOURCE 2: Paris Facts]" in result


def test_format_context_includes_chunk_text():
    chunks = [_make_chunk("Some important fact.")]
    result = format_context(chunks)
    assert "Some important fact." in result


def test_format_context_empty_list():
    result = format_context([])
    assert result == ""


def test_format_context_separator_between_chunks():
    chunks = [_make_chunk("First."), _make_chunk("Second.")]
    result = format_context(chunks)
    # The two source blocks must be separated by a blank line.
    assert "\n\n" in result


# ── assemble_context ──────────────────────────────────────────────────────────

def test_assemble_context_returns_all_chunks_when_within_budget():
    chunks = [_make_chunk("Short text."), _make_chunk("Also short.")]
    context_text, selected = assemble_context(chunks, max_tokens=10_000)
    assert len(selected) == 2
    assert "Short text." in context_text
    assert "Also short." in context_text


def test_assemble_context_stops_when_budget_exceeded():
    # Each token is roughly 1 word.  Create a chunk large enough to exceed a
    # tiny budget when combined with a second chunk.
    chunk1 = _make_chunk("word " * 20)  # ~20 tokens
    chunk2 = _make_chunk("more " * 20)  # ~20 tokens
    # Budget of 25 tokens fits chunk1 but not chunk1 + chunk2.
    context_text, selected = assemble_context([chunk1, chunk2], max_tokens=25)
    assert len(selected) == 1
    assert selected[0].text == chunk1.text


def test_assemble_context_empty_chunks():
    context_text, selected = assemble_context([], max_tokens=6000)
    assert context_text == ""
    assert selected == []


def test_assemble_context_preserves_rank_order():
    """Higher-ranked chunks (index 0) must always be selected first."""
    high = _make_chunk("High relevance content.", title="High")
    low = _make_chunk("Low relevance content.", title="Low")
    # Make budget tight enough to allow only one chunk.
    budget = count_tokens(high.text) + 1
    _, selected = assemble_context([high, low], max_tokens=budget)
    assert len(selected) == 1
    assert selected[0].document_title == "High"


# ── extract_citations ─────────────────────────────────────────────────────────

def test_extract_citations_returns_list_of_dicts():
    chunks = [_make_chunk("Some text.", title="My Doc")]
    citations = extract_citations(chunks)
    assert isinstance(citations, list)
    assert len(citations) == 1


def test_extract_citations_has_required_keys():
    chunks = [_make_chunk("Some text.", chunk_index=3, title="My Doc")]
    citation = extract_citations(chunks)[0]
    assert "doc_id" in citation
    assert "doc_title" in citation
    assert "chunk_index" in citation
    assert "excerpt" in citation


def test_extract_citations_doc_id_is_string():
    """doc_id must be a string UUID (serialisable for JSONB and SSE)."""
    chunks = [_make_chunk("Text.")]
    citation = extract_citations(chunks)[0]
    assert isinstance(citation["doc_id"], str)
    # Must be parseable back to UUID.
    uuid.UUID(citation["doc_id"])


def test_extract_citations_excerpt_truncated_to_200():
    long_text = "x" * 500
    chunks = [_make_chunk(long_text)]
    citation = extract_citations(chunks)[0]
    assert len(citation["excerpt"]) == 200


def test_extract_citations_excerpt_short_text_not_padded():
    short_text = "Short."
    chunks = [_make_chunk(short_text)]
    citation = extract_citations(chunks)[0]
    assert citation["excerpt"] == short_text


def test_extract_citations_multiple_chunks():
    chunks = [_make_chunk(f"Text {i}.") for i in range(3)]
    citations = extract_citations(chunks)
    assert len(citations) == 3


def test_extract_citations_correct_metadata():
    chunk = _make_chunk("Content here.", chunk_index=7, title="The Book")
    citation = extract_citations([chunk])[0]
    assert citation["doc_title"] == "The Book"
    assert citation["chunk_index"] == 7
    assert citation["doc_id"] == str(_DOC_ID)
