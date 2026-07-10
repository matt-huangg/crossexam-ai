"""Fetch published California OAH special-education due process decisions.

Corpus scope (locked): see ``docs/oah-decision-corpus.md``.

  - Forum: CA OAH Special Education Division (statewide)
  - MVP filter: San Diego Unified (+ nearby LEAs if needed)
  - MVP window: last ~5 years (expandable to OAH searchable set 2013→present)
  - Source of truth: official OAH PDFs only
  - Extraction: deterministic (pymupdf) — never LLM paraphrase of the body

Why this file exists separately from fetch_statute.py / fetch_cfr.py:

  Decisions are multi-page PDFs with captions, issues, findings, and orders —
  not neatly sectioned CFR/XML. The pipeline shape is the same
  (fetch → cache raw → parse → processed JSON → chunk → Chroma), but the
  parsers and metadata (case_id, lea, decision_date) differ.

Official entry points:

  - Search/instructions:
    https://www.dgs.ca.gov/OAH/Case-Types/Special-Education/Services/Page-Content/Special-Education-Services-List-Folder/Search-Special-Education-Decisions-and-Orders
  - Decisions listing / PDF tree under
    /media/Divisions/OAH/Special-Education/SE-Decisions/{year}/...
  - Box.com bulk dump (fallback):
    https://dgscloud.box.com/s/05yxfqlaa08743v0kic30pmvzphsys2i
"""

from __future__ import annotations

from pathlib import Path

import httpx

from cache import PROCESSED_DIR, RAW_DIR, load_models, save_models
from models import HearingDecision

# Prefer San Diego Unified for the MVP slice; widen only if the set is too thin.
DEFAULT_LEA_FILTERS = (
    "San Diego Unified",
    # Uncomment nearby LEAs later if needed:
    # "Grossmont",
    # "Poway",
    # "Sweetwater",
)

DECISIONS_RAW_DIR = RAW_DIR / "decisions"
DECISIONS_PROCESSED_PATH = PROCESSED_DIR / "oah-decisions.json"

# OAH decision PDFs are typically named with the case number, e.g.
# 2024090930-AccMod.pdf under a year/month folder.
OAH_DECISIONS_MEDIA_ROOT = (
    "https://www.dgs.ca.gov/-/media/Divisions/OAH/Special-Education/SE-Decisions"
)


def list_candidate_pdf_urls(
    *,
    lea_filters: tuple[str, ...] = DEFAULT_LEA_FILTERS,
    years: list[int] | None = None,
) -> list[str]:
    """Return absolute URLs of OAH decision PDFs to download for the MVP slice.

    TODO(you):
      1. Decide discovery strategy (pick one and document why):
         a. Scrape/paginate the OAH Decisions listing pages and filter
            links whose preview/caption mentions an lea_filters string, or
         b. Download the Box.com bulk set, then filter locally by extracted
            caption text (more reliable if HTML search is flaky).
      2. Restrict to ``years`` (default: last 5 calendar years).
      3. Prefer ``*Acc.pdf`` / ``*AccMod.pdf`` decision-after-hearing files;
         skip settlement-only and generic order PDFs.
      4. Return deduplicated absolute https URLs.

    Do not use third-party aggregators as the source of truth.
    """
    raise NotImplementedError


def download_pdf(url: str, dest: Path) -> Path:
    """Download one PDF to ``dest`` (under data/raw/decisions/).

    TODO(you):
      1. GET ``url`` with httpx (set a User-Agent; some gov sites are picky).
      2. raise_for_status(); write bytes to dest.
      3. Return dest.
    """
    raise NotImplementedError


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text from a decision PDF with pymupdf (deterministic).

    TODO(you):
      1. ``import fitz`` (pymupdf) and open pdf_path.
      2. Concatenate page.get_text() for every page, with newlines between pages.
      3. Return the full string. Do not summarize or rewrite.

    If extraction returns near-empty text (scanned image PDF), fail visibly
    rather than silently storing garbage — we can add OCR later if needed.
    """
    raise NotImplementedError


def parse_decision(pdf_path: Path, text: str, source_url: str) -> HearingDecision:
    """Build a HearingDecision from extracted text + filename/URL metadata.

    TODO(you):
      1. Parse case_id from the filename stem (e.g. ``2024090930`` from
         ``2024090930-AccMod.pdf``) — more stable than scraping the body.
      2. Pull lea from the caption lines near the top of ``text``
         (regex / line scan for \"School District\" / known LEA names).
      3. Pull decision_date if present (ISO YYYY-MM-DD when possible).
      4. heading = first meaningful caption line or f\"OAH {case_id}\".
      5. citation = f\"OAH {case_id}\".
      6. Return HearingDecision(...). Pydantic will reject empty text.

    Filtering by DEFAULT_LEA_FILTERS can happen here or in list_candidate_pdf_urls
    — prefer filtering early to avoid downloading irrelevant statewide PDFs.
    """
    raise NotImplementedError


def main(*, use_cache: bool = True) -> list[HearingDecision]:
    """Fetch/parse MVP San Diego–area OAH decisions into processed JSON.

    Cache layers mirror the federal-law fetchers:
      data/raw/decisions/*.pdf  → raw PDFs
      data/processed/oah-decisions.json → HearingDecision list
    """
    if use_cache:
        cached = load_models(DECISIONS_PROCESSED_PATH, HearingDecision)
        if cached is not None:
            return cached

    DECISIONS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    urls = list_candidate_pdf_urls()
    decisions: list[HearingDecision] = []

    for url in urls:
        # Filename from the URL path keeps case_id recoverable offline.
        name = url.rstrip("/").split("/")[-1]
        dest = DECISIONS_RAW_DIR / name
        if not dest.exists():
            download_pdf(url, dest)
        text = extract_text_from_pdf(dest)
        decisions.append(parse_decision(dest, text, source_url=url))

    if use_cache:
        save_models(DECISIONS_PROCESSED_PATH, decisions)
    return decisions


if __name__ == "__main__":
    # Stub entrypoint — will raise until list_candidate_pdf_urls is implemented.
    results = main()
    print(f"Parsed {len(results)} OAH decisions")
    for d in results[:5]:
        print(f"  {d.citation}: {d.lea} ({d.decision_date})")
