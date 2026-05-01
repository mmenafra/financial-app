"""Shared PDF text extraction (pypdf)."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF using pypdf."""
    logger.debug("PDF: opening reader, size=%s bytes", len(pdf_bytes))
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - env guard
        raise ValueError("PDF support is not installed (pypdf missing).") from exc

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.error("PDF: could not read file: %s", exc)
        raise ValueError("Could not read PDF file.") from exc

    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text()
        except Exception as exc:
            logger.error("PDF: could not extract text from page %s: %s", i, exc)
            raise ValueError("Could not extract text from PDF page.") from exc
        if t:
            parts.append(t)
        else:
            logger.warning("PDF: page %s yielded no text", i)
    return "\n".join(parts)
