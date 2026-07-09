"""Shared record shapes used across the ingestion pipeline.

Keeping this separate (rather than defining LegalSection inside fetch_cfr.py
or fetch_statute.py) means chunk.py and build_index.py (later concepts) can
depend on one stable shape regardless of which fetcher produced it.

Uses pydantic rather than a plain dataclass for two reasons:
  1. Runtime validation - if a bug in parse_sections() ever produces a
     malformed record (empty citation, near-empty text), pydantic rejects
     it at construction time, right where the bad data was created -
     instead of silently flowing into chunk.py and failing confusingly
     two steps later.
  2. Free JSON serialization (.model_dump_json() / .model_validate_json()),
     which we'll want once build_index.py starts caching intermediate
     records to data/processed/ as JSON.

This is also the same pattern (pydantic BaseModel = structured schema) used
later for LLM structured outputs in backend/, so the mental model transfers.
"""

from typing import Literal

from pydantic import BaseModel, Field


class LegalSection(BaseModel):
    """One retrievable unit of statute/regulation text, before chunking.

    This is the common output shape for both fetch_cfr.py and
    fetch_statute.py, even though they get their raw data very differently
    (a JSON/XML API vs. scraped HTML).

    source_type distinguishes the two layers of federal law in this corpus:

      - ``"statute"`` — primary law enacted by Congress (U.S. Code).
        Here: 20 U.S.C. Chapter 33 (IDEA), from fetch_statute.py.
        Citations look like ``20 U.S.C. § 1415``.

      - ``"cfr"`` — agency regulations that implement statutes (Code of
        Federal Regulations). Here: 34 CFR Part 300 (special-education
        regs under IDEA), from fetch_cfr.py. Citations look like
        ``34 CFR § 300.503``.
    """

    source_type: Literal["statute", "cfr"]
    citation: str = Field(min_length=1)      # e.g. "34 CFR § 300.503" or "20 U.S.C. § 1415"
    heading: str = Field(min_length=1)        # section title, e.g. "Prior notice by the public agency"
    text: str = Field(min_length=1)            # full section body text
    source_url: str = Field(min_length=1)       # where this was fetched from, for traceability
