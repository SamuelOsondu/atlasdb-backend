"""
Text extractors for supported document types.
Each extractor receives raw file bytes and returns plain text.
"""
import io
import re


def extract_pdf(content: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        parts = [page.extract_text() for page in pdf.pages if page.extract_text()]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def extract_markdown(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)        # headings
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)       # bold/italic *
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)         # bold/italic _
    text = re.sub(r"```[\s\S]*?```", "", text)                     # fenced code
    text = re.sub(r"`[^`\n]+`", "", text)                          # inline code
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)         # links
    text = re.sub(r"<[^>]+>", "", text)                            # HTML tags
    text = re.sub(r"\n{3,}", "\n\n", text)                         # normalize spacing
    return text.strip()


def extract_txt(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").strip()


_EXTRACTORS = {
    "application/pdf": extract_pdf,
    "text/plain": extract_txt,
    "text/markdown": extract_markdown,
    "text/x-markdown": extract_markdown,
}


def extract_text_from_content(content: bytes, mime_type: str) -> str:
    fn = _EXTRACTORS.get(mime_type)
    if fn is None:
        raise ValueError(f"No extractor for MIME type: {mime_type}")
    return fn(content)
