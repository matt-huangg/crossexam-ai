"""Shared record shapes used across the ingestion pipeline.

Keeping this separate (rather than defining LegalSection / HearingDecision
inside federal/ or oah/ modules) means pipeline/chunk.py and
pipeline/build_index.py can depend on one stable shape regardless of which
fetcher produced it.

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


class HearingDecision(BaseModel):
    """One published OAH due process decision, before chunking.

    Parallel to LegalSection, but for administrative hearing decisions
    (Corpus 2). Text must be the exact extracted PDF/HTML body — never an
    LLM paraphrase. Optional enrichment fields (tags, summaries) belong
    elsewhere and must not replace ``text`` as the citable passage.

    See ``docs/oah-decision-corpus.md`` for statewide California OAH scope.
    """

    source_type: Literal["decision"] = "decision"
    # OAH case number as used in filenames / captions, e.g. "2024090930".
    case_id: str = Field(min_length=1)
    citation: str = Field(min_length=1)  # e.g. "OAH 2024090930"
    # Local educational agency named in the caption, e.g. "San Diego Unified School District".
    lea: str = Field(min_length=1)
    # ISO date when available (YYYY-MM-DD); empty string only if truly unknown after parse.
    decision_date: str = Field(default="")
    heading: str = Field(min_length=1)  # short title / caption line
    text: str = Field(min_length=1)  # full extracted decision body
    source_url: str = Field(min_length=1)


class LegalChunk(BaseModel):
    """One retrieval-sized piece of statute, CFR, or OAH decision text.

    Long sources are split so similarity search returns a focused passage
    rather than an entire multi-page section or decision. Short sources
    stay as a single chunk (chunk_index=0, chunk_count=1).

    Every chunk keeps the parent citation/heading/source_url so a retrieved
    hit can be traced back to the authoritative source without joining
    another table. Decision chunks also carry ``case_id`` / ``lea`` /
    ``decision_date`` (empty strings for statute/CFR).
    """

    chunk_id: str = Field(min_length=1)  # stable id, e.g. "34 CFR § 300.503#0"
    source_type: Literal["statute", "cfr", "decision"]
    citation: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    text: str = Field(min_length=1)  # chunk body (may include a citation prefix)
    source_url: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    chunk_count: int = Field(ge=1)
    # Populated for OAH decision chunks; empty for federal-law chunks.
    case_id: str = Field(default="")
    lea: str = Field(default="")
    decision_date: str = Field(default="")
