"""Context assembly utilities for the query engine.

Responsibilities:
  - Count tokens in a text string using tiktoken (cl100k_base).
  - Greedily select top-ranked retrieval chunks that fit within the token budget.
  - Format the selected chunks into a structured context string.
  - Extract citations (document references) from the selected chunks.

Design notes:
  - ``assemble_context`` respects both the token budget (``max_tokens``) and the
    ordering of ``chunks`` (already ranked by descending similarity score from
    the retrieval service).  It stops as soon as adding the next chunk would
    exceed the budget, so higher-ranked chunks are always preferred.
  - Token counting is synchronous and in-memory — no network calls required.
  - ``extract_citations`` limits excerpts to 200 characters to keep the SSE
    payload and the JSONB column compact.
"""
import tiktoken

from app.retrieval.schemas import SearchResult

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return the number of cl100k_base tokens in *text*."""
    return len(_ENCODING.encode(text))


def format_context(chunks: list[SearchResult]) -> str:
    """Format a list of chunks as a numbered, source-labelled context block.

    Example output::

        [SOURCE 1: Europe Travel Guide]
        Paris is the capital of France...

        [SOURCE 2: World Atlas]
        France is a country in Western Europe...

    Args:
        chunks: Ordered list of retrieval results to include in the context.

    Returns:
        Multi-line string suitable for embedding in the system prompt.
    """
    parts = [
        f"[SOURCE {i}: {chunk.document_title}]\n{chunk.text}"
        for i, chunk in enumerate(chunks, start=1)
    ]
    return "\n\n".join(parts)


def assemble_context(
    chunks: list[SearchResult],
    max_tokens: int,
) -> tuple[str, list[SearchResult]]:
    """Greedily select chunks that fit within *max_tokens* and format them.

    Iterates through *chunks* in order (assumed highest-score first).  Stops
    as soon as adding the next chunk would push the running total over the
    budget.  This ensures the most relevant content is always included.

    Args:
        chunks:     Ranked retrieval results (highest similarity first).
        max_tokens: Token budget for the context block.

    Returns:
        A tuple of:
          - ``context_text``: formatted context string for the system prompt.
          - ``selected``:     subset of *chunks* that fit within the budget.
    """
    selected: list[SearchResult] = []
    token_count = 0

    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.text)
        if token_count + chunk_tokens > max_tokens:
            break
        selected.append(chunk)
        token_count += chunk_tokens

    context_text = format_context(selected)
    return context_text, selected


def extract_citations(chunks: list[SearchResult]) -> list[dict]:
    """Convert retrieved chunks into serialisable citation dicts.

    Each citation matches the ``CitationSchema`` shape defined in
    ``app.shared.schemas`` so it can be stored in the JSONB ``citations``
    column on ``Message`` and returned as-is in the SSE done event.

    Args:
        chunks: The chunks that were actually used in the LLM context.

    Returns:
        List of dicts with keys: ``doc_id``, ``doc_title``, ``chunk_index``,
        ``excerpt`` (first 200 characters of the chunk text).
    """
    return [
        {
            "doc_id": str(chunk.document_id),
            "doc_title": chunk.document_title,
            "chunk_index": chunk.chunk_index,
            "excerpt": chunk.text[:200],
        }
        for chunk in chunks
    ]
