"""Split LegalSection / HearingDecision records into LegalChunk records.

Why chunk at all: embedding an entire multi-page section or a full OAH
decision makes similarity search return a giant blob. Downstream personas
need a focused, citable passage - not a whole chapter.

Strategies (deterministic, no LLM - see ../../ARCHITECTURE.md):

  Federal statute / CFR
    1. Split on lettered subsections: (a), (b), (c)...
    2. Pack consecutive subsections together up to TARGET_CHARS.

  OAH decisions (prose, no lettered subsections)
    1. Split on paragraph boundaries (blank lines).
    2. Pack consecutive paragraphs up to TARGET_CHARS.
    3. Overlap consecutive chunks by OVERLAP_CHARS.
"""

from __future__ import annotations

import hashlib
import re

from ingest.cache import PROCESSED_DIR, load_models, load_processed, save_models
from ingest.models import HearingDecision, LegalChunk, LegalSection

STATUTE_PROCESSED_PATH = PROCESSED_DIR / "20-usc-ch33.json"
CFR_PROCESSED_PATH = PROCESSED_DIR / "34-cfr-300.json"
DECISIONS_PROCESSED_PATH = PROCESSED_DIR / "oah-decisions.json"
CHUNKS_PATH = PROCESSED_DIR / "chunks.json"

TARGET_CHARS = 3500
HARD_MAX_CHARS = 6000
OVERLAP_CHARS = 400

# Matches a lettered subsection marker at the start of a line: "(a) ", "(b) ".
# (?m) makes ^ match every line start, not just the start of the string.
# [a-z] deliberately excludes "(1)" numbered paragraphs, so they stay
# attached to whichever lettered subsection they belong under.
SUBSECTION_RE = re.compile(r"(?m)^(\([a-z]\)\s)")


def _split_subsections(text: str) -> list[str]:
    """Split section body on lettered subsection markers; keep markers attached."""
    parts = SUBSECTION_RE.split(text.strip())
    blocks: list[str] = []
    if parts[0].strip():
        blocks.append(parts[0].strip())
    for i in range(1, len(parts), 2):
        marker = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        blocks.append(f"{marker}{body}".strip())
    return blocks


def _pack_blocks(blocks: list[str], target_chars: int) -> list[str]:
    """Pack consecutive blocks together into chunks near target_chars."""
    packed: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        added_len = len(block) + (1 if current else 0)  # +1 for the join newline
        if current and current_len + added_len > target_chars:
            packed.append("\n".join(current))
            current = []
            current_len = 0
        current.append(block)
        current_len += len(block) if not current_len else added_len

    if current:
        packed.append("\n".join(current))
    return packed


def chunk_section(section: LegalSection) -> list[LegalChunk]:
    """Turn one LegalSection into one or more LegalChunks."""
    body = section.text.strip()

    if len(body) <= TARGET_CHARS:
        bodies = [body]
    else:
        blocks = _split_subsections(body)
        bodies = _pack_blocks(blocks, TARGET_CHARS)

    chunk_count = len(bodies)
    chunks: list[LegalChunk] = []
    for index, chunk_body in enumerate(bodies):
        chunks.append(
            LegalChunk(
                chunk_id=f"{section.citation}#{index}",
                source_type=section.source_type,
                citation=section.citation,
                heading=section.heading,
                text=f"{section.citation} — {section.heading}\n\n{chunk_body}",
                source_url=section.source_url,
                chunk_index=index,
                chunk_count=chunk_count,
            )
        )
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split prose on blank lines; fall back to single newlines if needed.

    OAH PDFs are narrative — no reliable (a)/(b) structure — so paragraph
    breaks are the best deterministic boundary we have.
    """
    text = text.strip()
    if not text:
        return []

    blocks = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(blocks) >= 2:
        return blocks

    # Some extracts are single-spaced with no blank lines — use line breaks.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines if lines else [text]


def _overlap_tail(text: str, overlap_chars: int) -> str:
    """Trailing slice for the next chunk, broken on a newline when possible."""
    if overlap_chars <= 0 or not text:
        return ""
    if len(text) <= overlap_chars:
        return text

    tail = text[-overlap_chars:]
    # Prefer starting at a line boundary so the duplicated prefix is readable.
    newline = tail.find("\n")
    if newline != -1 and newline + 1 < len(tail):
        return tail[newline + 1 :]
    return tail


def _apply_overlap(bodies: list[str], overlap_chars: int) -> list[str]:
    """Prepend each chunk (after the first) with the previous chunk's tail.

    Overlap is taken from the *non-overlapped* packed bodies so successive
    windows don't compound (chunk 2 does not inherit chunk 0 via chunk 1).
    """
    if len(bodies) <= 1 or overlap_chars <= 0:
        return bodies

    overlapped: list[str] = [bodies[0]]
    for i in range(1, len(bodies)):
        # Source from prior packed body, not already-overlapped output.
        tail = _overlap_tail(bodies[i - 1], overlap_chars)
        combined = f"{tail}\n\n{bodies[i]}" if tail else bodies[i]
        overlapped.append(combined)
    return overlapped


def chunk_decision(decision: HearingDecision) -> list[LegalChunk]:
    """Turn one HearingDecision into one or more overlapping LegalChunks.

    Decisions lack lettered subsection structure, so we pack paragraphs and
    overlap consecutive chunks. Heading on the chunk is the LEA name (stable
    and more useful for retrieval than the caption party line).
    """
    body = decision.text.strip()

    if len(body) <= TARGET_CHARS:
        bodies = [body]
    else:
        blocks = _split_paragraphs(body)
        packed = _pack_blocks(blocks, TARGET_CHARS)
        bodies = _apply_overlap(packed, OVERLAP_CHARS)

    chunk_count = len(bodies)
    # MediaSearch sometimes lists corrected / alternate PDFs under one case
    # number. Chroma ids must be unique, so include a short source-url token.
    url_token = hashlib.sha1(decision.source_url.encode("utf-8")).hexdigest()[:8]
    id_stem = f"{decision.citation}#{url_token}"

    chunks: list[LegalChunk] = []
    for index, chunk_body in enumerate(bodies):
        date_bit = f" ({decision.decision_date})" if decision.decision_date else ""
        chunks.append(
            LegalChunk(
                chunk_id=f"{id_stem}#{index}",
                source_type="decision",
                citation=decision.citation,
                heading=decision.lea,
                text=(
                    f"{decision.citation} — {decision.lea}{date_bit}\n\n"
                    f"{chunk_body}"
                ),
                source_url=decision.source_url,
                chunk_index=index,
                chunk_count=chunk_count,
                case_id=decision.case_id,
                lea=decision.lea,
                decision_date=decision.decision_date,
            )
        )
    return chunks


def chunk_sections(sections: list[LegalSection]) -> list[LegalChunk]:
    """Chunk every federal section in order."""
    chunks: list[LegalChunk] = []
    for section in sections:
        chunks.extend(chunk_section(section))
    return chunks


def chunk_decisions(decisions: list[HearingDecision]) -> list[LegalChunk]:
    """Chunk every OAH decision in order."""
    chunks: list[LegalChunk] = []
    for decision in decisions:
        chunks.extend(chunk_decision(decision))
    return chunks


def main() -> list[LegalChunk]:
    """Load cached sources, chunk them, and write `chunks.json`."""
    statute = load_processed(STATUTE_PROCESSED_PATH)
    cfr = load_processed(CFR_PROCESSED_PATH)
    decisions = load_models(DECISIONS_PROCESSED_PATH, HearingDecision)

    missing: list[str] = []
    if statute is None:
        missing.append(str(STATUTE_PROCESSED_PATH))
    if cfr is None:
        missing.append(str(CFR_PROCESSED_PATH))
    if decisions is None:
        missing.append(str(DECISIONS_PROCESSED_PATH))
    if missing:
        raise FileNotFoundError(
            "Missing processed cache. Run federal fetchers and "
            f"`python -m ingest.oah.fetch` first. Missing: {', '.join(missing)}"
        )

    chunks = chunk_sections(statute + cfr) + chunk_decisions(decisions)
    save_models(CHUNKS_PATH, chunks)
    return chunks


if __name__ == "__main__":
    all_chunks = main()
    statute_n = sum(1 for c in all_chunks if c.source_type == "statute")
    cfr_n = sum(1 for c in all_chunks if c.source_type == "cfr")
    decision_n = sum(1 for c in all_chunks if c.source_type == "decision")
    print(f"Wrote {len(all_chunks)} chunks -> {CHUNKS_PATH}")
    print(f"  statute: {statute_n}  cfr: {cfr_n}  decision: {decision_n}")
