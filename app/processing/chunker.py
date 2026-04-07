"""
Token-aware text chunker using tiktoken (cl100k_base encoding).

Strategy:
  1. Encode the full text into a flat token stream, preserving paragraph breaks.
  2. Slide a window of `max_tokens` tokens, advancing by `max_tokens - overlap`
     each step. This produces overlapping chunks that share context at boundaries.
"""
import re

import tiktoken

_ENCODING = "cl100k_base"


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap: int = 50,
) -> list[str]:
    """
    Split `text` into overlapping token-bounded chunks.

    Returns an empty list if the text produces no tokens.
    Raises ValueError if overlap >= max_tokens.
    """
    if overlap >= max_tokens:
        raise ValueError(f"overlap ({overlap}) must be less than max_tokens ({max_tokens})")

    enc = tiktoken.get_encoding(_ENCODING)
    sep_tokens = enc.encode("\n\n")

    # Build flat token list preserving paragraph structure.
    all_tokens: list[int] = []
    for i, para in enumerate(re.split(r"\n{2,}", text)):
        para = para.strip()
        if not para:
            continue
        if i > 0 and all_tokens:
            all_tokens.extend(sep_tokens)
        all_tokens.extend(enc.encode(para))

    if not all_tokens:
        return []

    step = max_tokens - overlap
    chunks: list[str] = []
    start = 0
    total = len(all_tokens)

    while start < total:
        end = min(start + max_tokens, total)
        decoded = enc.decode(all_tokens[start:end]).strip()
        if decoded:
            chunks.append(decoded)
        if end >= total:
            break
        start += step

    return chunks
