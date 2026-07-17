"""Orchestrate OAH decision ingest: discover → download → parse.

Thin entrypoint. Heavy lifting lives in:

  - ``ingest.oah.discovery`` — MediaSearch PDF listing
  - ``ingest.oah.pdf``       — download + pymupdf extract
  - ``ingest.oah.parse``     — HearingDecision (+ optional LEA filter)

Corpus scope: ``docs/oah-decision-corpus.md`` (statewide CA OAH, ~5-year window).
"""

from __future__ import annotations

import httpx

from ingest.cache import PROCESSED_DIR, RAW_DIR, load_models, save_models
from ingest.models import HearingDecision
from ingest.oah.discovery import list_candidate_pdf_urls
from ingest.oah.parse import matches_lea_filters, parse_decision
from ingest.oah.pdf import download_pdf, extract_text_from_pdf

DECISIONS_RAW_DIR = RAW_DIR / "decisions"
DECISIONS_PROCESSED_PATH = PROCESSED_DIR / "oah-decisions.json"


def main(
    *,
    use_cache: bool = True,
    lea_filters: tuple[str, ...] = (),
) -> list[HearingDecision]:
    """Fetch/parse statewide CA OAH decisions into processed JSON.

    By default keeps every AccMod-ish PDF in the discovery year window.
    Pass ``lea_filters`` (e.g. ``("San Diego Unified",)``) only when you
    want an optional district slice; LEA is always stored on each record.

    Cache:
      data/raw/decisions/*.pdf           — raw PDFs
      data/processed/oah-decisions.json  — HearingDecision list
    """
    if use_cache:
        cached = load_models(DECISIONS_PROCESSED_PATH, HearingDecision)
        if cached is not None:
            return cached

    DECISIONS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    decisions: list[HearingDecision] = []

    for candidate in list_candidate_pdf_urls():
        # UUID media paths have no case_id — save under the display filename.
        dest = DECISIONS_RAW_DIR / candidate.filename.replace("/", "_").replace(
            "\\", "_"
        )
        try:
            if not dest.exists():
                download_pdf(candidate.url, dest)
            text = extract_text_from_pdf(dest)
            decision = parse_decision(
                dest, text, candidate.url, lea_filters=lea_filters
            )
        except (httpx.HTTPError, ValueError, OSError) as exc:
            print(f"  skip {dest.name}: {exc}")
            continue

        # Empty lea_filters → keep all; non-empty → optional district slice.
        if matches_lea_filters(decision.text, decision.lea, lea_filters):
            decisions.append(decision)

    save_models(DECISIONS_PROCESSED_PATH, decisions)
    return decisions


if __name__ == "__main__":
    print("Listing MediaSearch candidates (last ~5 years)...")
    candidates = list_candidate_pdf_urls()
    print(f"  {len(candidates)} AccMod-ish PDFs in year window")
    for c in candidates[:5]:
        print(f"  - {c.filename}")

    print("\nFetching + parsing statewide CA OAH decisions (downloads PDFs)...")
    results = main(use_cache=False)
    print(f"Parsed {len(results)} OAH decisions")
    for d in results[:5]:
        print(f"  {d.citation}: {d.lea} ({d.decision_date})")
