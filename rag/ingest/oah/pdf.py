"""Download OAH decision PDFs and extract plain text.

Deterministic only (httpx + pymupdf). No summarization — extracted text is
what later gets chunked and cited as source of truth.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf
import httpx

MIN_EXTRACTED_TEXT_CHARS = 50


def download_pdf(url: str, dest: Path) -> Path:
    """Download one PDF to ``dest`` (typically under data/raw/decisions/)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
        timeout=60.0,
    )
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text with pymupdf (exact page text, no rewrite).

    Raises ValueError if almost no text is extracted (likely a scanned PDF).
    """
    with fitz.open(pdf_path) as doc:
        text = "\n".join(page.get_text() for page in doc)

    if len(text.strip()) < MIN_EXTRACTED_TEXT_CHARS:
        raise ValueError(
            f"Extracted text from {pdf_path.name} is too short "
            f"({len(text.strip())} chars); PDF may be scanned/image-only."
        )
    return text
