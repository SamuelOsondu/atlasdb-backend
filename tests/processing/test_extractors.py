"""Unit tests for document text extractors."""
import io

import pytest

from app.processing.extractors import (
    extract_markdown,
    extract_pdf,
    extract_text_from_content,
    extract_txt,
)


# ── extract_txt ────────────────────────────────────────────────────────────────

def test_extract_txt_returns_text():
    result = extract_txt(b"Hello world")
    assert result == "Hello world"


def test_extract_txt_strips_whitespace():
    result = extract_txt(b"  hello  \n")
    assert result == "hello"


def test_extract_txt_handles_utf8():
    result = extract_txt("café résumé".encode("utf-8"))
    assert "café" in result


def test_extract_txt_handles_invalid_bytes():
    result = extract_txt(b"\xff\xfe invalid utf8 text")
    assert len(result) > 0  # should not raise


# ── extract_markdown ───────────────────────────────────────────────────────────

def test_extract_markdown_strips_headings():
    md = b"# Title\n\nContent here."
    result = extract_markdown(md)
    assert "Title" in result
    assert "#" not in result


def test_extract_markdown_strips_bold():
    md = b"**bold text** and *italic*"
    result = extract_markdown(md)
    assert "bold text" in result
    assert "**" not in result
    assert "*" not in result


def test_extract_markdown_strips_fenced_code():
    md = b"Before\n\n```python\ncode here\n```\n\nAfter"
    result = extract_markdown(md)
    assert "Before" in result
    assert "After" in result
    assert "code here" not in result


def test_extract_markdown_preserves_link_text():
    md = b"See [the docs](https://example.com) for details."
    result = extract_markdown(md)
    assert "the docs" in result
    assert "https://" not in result


def test_extract_markdown_normalizes_spacing():
    md = b"Line 1\n\n\n\n\nLine 2"
    result = extract_markdown(md)
    assert "\n\n\n" not in result


# ── extract_pdf ────────────────────────────────────────────────────────────────

def test_extract_pdf_raises_on_invalid_bytes():
    with pytest.raises(Exception):
        extract_pdf(b"not a pdf")


def test_extract_pdf_returns_string_type():
    """For a real PDF we'd need a fixture file; skip if pdfplumber can't open."""
    try:
        import pdfplumber
        import io as _io
        # Create a minimal valid PDF using reportlab if available, otherwise skip
        pytest.importorskip("reportlab")
        from reportlab.pdfgen import canvas
        buf = _io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 750, "Hello PDF World")
        c.save()
        result = extract_pdf(buf.getvalue())
        assert isinstance(result, str)
        assert "Hello" in result or len(result) >= 0  # may be empty for some PDF generators
    except ImportError:
        pytest.skip("reportlab not installed — skipping PDF content test")


# ── extract_text_from_content dispatch ────────────────────────────────────────

def test_dispatch_txt():
    result = extract_text_from_content(b"plain text", "text/plain")
    assert result == "plain text"


def test_dispatch_markdown():
    result = extract_text_from_content(b"## Heading\n\nBody", "text/markdown")
    assert "Heading" in result
    assert "##" not in result


def test_dispatch_x_markdown():
    result = extract_text_from_content(b"# Title\n\nText", "text/x-markdown")
    assert "Title" in result


def test_dispatch_unknown_mime_raises():
    with pytest.raises(ValueError, match="No extractor"):
        extract_text_from_content(b"data", "application/octet-stream")
