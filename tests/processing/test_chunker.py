"""Unit tests for the token-aware text chunker."""
import pytest

from app.processing.chunker import chunk_text


def test_empty_text_returns_empty_list():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty_list():
    assert chunk_text("   \n\n   ") == []


def test_short_text_returns_single_chunk():
    chunks = chunk_text("Hello world", max_tokens=512, overlap=50)
    assert len(chunks) == 1
    assert "Hello world" in chunks[0]


def test_chunk_count_correct_for_long_text():
    # Generate text that definitely exceeds one chunk.
    # Each word is ~1 token; 600 words >> 512 tokens.
    long_text = " ".join(f"word{i}" for i in range(600))
    chunks = chunk_text(long_text, max_tokens=512, overlap=50)
    assert len(chunks) >= 2


def test_overlap_causes_content_repetition():
    """Adjacent chunks share tokens due to overlap."""
    text = " ".join(f"word{i}" for i in range(600))
    chunks = chunk_text(text, max_tokens=100, overlap=20)
    # The last tokens of chunk[0] should appear at the start of chunk[1].
    if len(chunks) >= 2:
        end_of_first = chunks[0].split()[-5:]
        start_of_second = chunks[1].split()[:10]
        # At least some overlap words should appear in both
        overlap_count = sum(1 for w in end_of_first if w in start_of_second)
        assert overlap_count > 0


def test_each_chunk_within_token_limit():
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    long_text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_text(long_text, max_tokens=200, overlap=20)
    for chunk in chunks:
        assert len(enc.encode(chunk)) <= 200


def test_overlap_must_be_less_than_max_tokens():
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("some text", max_tokens=100, overlap=100)


def test_paragraph_boundaries_respected():
    """Text with clear paragraph breaks — output should not be empty."""
    text = "First paragraph content here.\n\nSecond paragraph content here.\n\nThird paragraph."
    chunks = chunk_text(text, max_tokens=512, overlap=10)
    assert len(chunks) >= 1
    full = " ".join(chunks)
    assert "First paragraph" in full
    assert "Second paragraph" in full


def test_single_paragraph_exceeding_limit_is_split():
    # One very long paragraph (no double newlines) exceeding max_tokens.
    long_para = " ".join(f"word{i}" for i in range(600))
    chunks = chunk_text(long_para, max_tokens=100, overlap=10)
    assert len(chunks) >= 2
    # All original words should be represented across chunks.
    full = " ".join(chunks)
    assert "word0" in full
    assert "word599" in full
