"""
File upload validation for the documents component.

Validates MIME type (with extension fallback for generic content_type values) and
enforces a configurable maximum file size by reading the upload in chunks — never
loading the entire file into memory before checking.
"""
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import AppValidationError, FileTooLargeError

# Supported MIME types and their canonical file-type label.
ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/x-markdown": "md",
}

# Extension → canonical MIME type mapping used when the client sends a generic
# MIME (e.g. "application/octet-stream") and we must rely on the file extension.
EXTENSION_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

# Number of bytes read per iteration when streaming the upload.
_CHUNK_SIZE: int = 1024 * 1024  # 1 MB


def _resolve_mime(content_type: str | None, filename: str | None) -> str:
    """
    Return the canonical MIME type or raise AppValidationError.

    Primary:  content_type sent by the client (parameters stripped).
    Fallback: file extension when the primary MIME is absent or not in our allow-list.
    """
    base_mime = (content_type or "").split(";")[0].strip().lower()

    if base_mime in ALLOWED_MIME_TYPES:
        return base_mime

    # Generic or absent MIME — try extension fallback.
    if filename:
        ext = Path(filename).suffix.lower()
        resolved = EXTENSION_TO_MIME.get(ext)
        if resolved and resolved in ALLOWED_MIME_TYPES:
            return resolved

    supported = ", ".join(sorted(ALLOWED_MIME_TYPES))
    raise AppValidationError(
        f"Unsupported file type '{base_mime}'. Supported types: {supported}",
        field="file",
    )


async def validate_and_read_upload(
    file: UploadFile,
    max_size_mb: int,
) -> tuple[bytes, str]:
    """
    Stream-read the upload, validate type and size, return (raw_bytes, mime_type).

    Raises:
        AppValidationError — unsupported file type.
        FileTooLargeError  — file exceeds max_size_mb.
    """
    mime_type = _resolve_mime(file.content_type, file.filename)

    max_bytes = max_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total_read = 0

    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_bytes:
            raise FileTooLargeError(
                f"File exceeds the {max_size_mb} MB maximum allowed size"
            )
        chunks.append(chunk)

    return b"".join(chunks), mime_type
