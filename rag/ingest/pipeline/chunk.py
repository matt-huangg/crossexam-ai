"""Split LegalSection / HearingDecision records into LegalChunk records.

Why chunk at all:

  Embedding an entire multi-page section (e.g. 20 U.S.C. § 1415 at ~43k
  chars) or a full OAH decision makes similarity search return a giant
  blob. Hearing officer / opposing counsel prompts need a focused passage
  they can cite.

Strategies (deterministic, no LLM):

  Federal statute / CFR
    1. Prefer legal structure: split on lettered subsections ``(a)``, ``(b)``.
    2. Pack consecutive blocks near TARGET_CHARS.
    3. Hard-split oversized blocks on newlines.

  OAH decisions (prose, no lettered subsections)
    1. Split on paragraph boundaries (blank lines).
    2. Pack near TARGET_CHARS.
    3. Overlap consecutive chunks by OVERLAP_CHARS so ideas on a boundary
       are less likely to be missed at retrieval time.

Every chunk text is prefixed with a cite line so the embedding carries the
cite and retrieved hits are self-describing in persona prompts.
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

# Soft target (~750–1000 tokens of English prose). We pack subsections up to
# this size so a chunk is useful for retrieval without being a whole chapter.
TARGET_CHARS = 3500
# Absolute ceiling after forced newline splits. Embedding models and prompt
# budgets both hate multi-page blobs; this is the "never go past here" guard.
HARD_MAX_CHARS = 6000
# Decision-only: trailing chars from the previous chunk prepended to the next
# so a thought sitting on a hard cut is still present in both embeddings.
OVERLAP_CHARS = 400

# Lettered subsection at the start of a line: "(a) Notice." / "(b) Types…"
# (?m) = multiline so ^ matches each line start, not just the string start.
# [a-z] deliberately excludes "(1)" / "(2)" numbered paragraphs so they stay
# attached to their parent lettered subsection.
SUBSECTION_RE = re.compile(r"(?m)^(\([a-z]\)\s)")


def _split_subsections(text: str) -> list[str]:
    """Split section body on lettered subsection starts; keep markers attached.

    Uses re.split with a capturing group so the ``(a) `` / ``(b) `` markers
    are preserved in the result (plain split would throw them away). Returns
    a list of blocks like ``["(a) …", "(b) …\\n(1) …", "(c) …"]``.
    """
    text = text.strip()
    if not text:
        return []

    parts = SUBSECTION_RE.split(text)
    # With a capturing group, split yields:
    #   [preamble, marker, body, marker, body, ...]
    # Preamble is text before the first (a) — uncommon but possible.
    blocks: list[str] = []
    if parts[0].strip():
        blocks.append(parts[0].strip())

    # Walk marker/body pairs: parts[1]=marker, parts[2]=body, parts[3]=marker, ...
    i = 1
    while i < len(parts):
        marker = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        # Re-attach the marker so the chunk still reads as legal text.
        blocks.append(f"{marker}{body}".strip())
        i += 2

    return blocks


def _split_paragraphs(text: str) -> list[str]:
    """Split prose on blank lines; fall back to single newlines if needed.

    OAH PDFs are narrative — paragraph breaks are the best deterministic
    boundary we have (no reliable ``(a)``/``(b)`` structure).
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


def _split_oversized(block: str, max_chars: int) -> list[str]:
    """Last-resort split on newlines when one block exceeds HARD_MAX_CHARS.

    Most lettered subsections / paragraphs fit under the hard max. This path
    only fires for unusually long single blocks — better a clean line break
    than a mid-word cut or an unembeddable blob.
    """
    if len(block) <= max_chars:
        return [block]

    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in block.splitlines():
        # +1 accounts for the newline we'll re-insert when joining.
        line_len = len(line) + (1 if current else 0)
        if current and current_len + line_len > max_chars:
            pieces.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += line_len
    if current:
        pieces.append("\n".join(current))
    return pieces


def _pack_blocks(blocks: list[str], target_chars: int, hard_max: int) -> list[str]:
    """Pack blocks into chunks near target_chars.

    Consecutive blocks stay together when they fit, so retrieval returns a
    coherent unit instead of an orphaned fragment. Soft target (not hard) on
    packing: slightly-over is preferred to leaving a tiny leftover alone.
    """
    packed: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        """Close the current bucket into `packed` and reset accumulators."""
        nonlocal current, current_len
        if current:
            packed.append("\n".join(current))
            current = []
            current_len = 0

    for block in blocks:
        # Oversized single blocks are pre-split; normal ones pass through
        # as a one-element list.
        for piece in _split_oversized(block, hard_max):
            piece_len = len(piece) + (1 if current else 0)
            # Next piece won't fit → seal this chunk and start a new one.
            if current and current_len + piece_len > target_chars:
                flush()
            current.append(piece)
            current_len += piece_len if current_len else len(piece)
            # A single piece already at/over target should not absorb neighbors.
            if current_len >= target_chars:
                flush()

    flush()  # don't drop the trailing partial bucket
    return packed


def _overlap_tail(text: str, overlap_chars: int) -> str:
    """Trailing slice for the next chunk, broken on a newline when possible.

    Prefer starting the overlap at a line boundary so the duplicated prefix
    is readable rather than mid-word.
    """
    if overlap_chars <= 0 or not text:
        return ""
    if len(text) <= overlap_chars:
        return text

    tail = text[-overlap_chars:]
    # Skip past a partial first line when a newline exists in the window.
    newline = tail.find("\n")
    if newline != -1 and newline + 1 < len(tail):
        return tail[newline + 1 :]
    return tail


def _apply_overlap(bodies: list[str], overlap_chars: int, hard_max: int) -> list[str]:
    """Prepend each chunk (after the first) with the previous chunk's tail.

    Overlap is taken from the *non-overlapped* packed bodies so successive
    windows don't compound (chunk 2 does not inherit chunk 0 via chunk 1).
    """
    if len(bodies) <= 1 or overlap_chars <= 0:
        return bodies

    overlapped: list[str] = [bodies[0]]
    for i in range(1, len(bodies)):
        # Source overlap from the prior packed body (not the already-overlapped
        # output) so each boundary duplicates only once.
        tail = _overlap_tail(bodies[i - 1], overlap_chars)
        combined = f"{tail}\n\n{bodies[i]}" if tail else bodies[i]
        if len(combined) > hard_max and tail:
            # Keep the overlap + as much new text as fits under the ceiling.
            room = max(0, hard_max - len(tail) - 2)
            combined = f"{tail}\n\n{bodies[i][:room]}" if room else tail[:hard_max]
        elif len(combined) > hard_max:
            combined = combined[:hard_max]
        overlapped.append(combined)
    return overlapped


def _format_section_chunk_text(section: LegalSection, body: str) -> str:
    """Prefix federal chunk body with citation + heading."""
    return f"{section.citation} — {section.heading}\n\n{body.strip()}"


def _format_decision_chunk_text(decision: HearingDecision, body: str) -> str:
    """Prefix decision chunk with cite, LEA, and date for embed + display."""
    date_bit = f" ({decision.decision_date})" if decision.decision_date else ""
    return (
        f"{decision.citation} — {decision.lea}{date_bit}\n\n{body.strip()}"
    )


def chunk_section(
    section: LegalSection,
    *,
    target_chars: int = TARGET_CHARS,
    hard_max_chars: int = HARD_MAX_CHARS,
) -> list[LegalChunk]:
    """Turn one LegalSection into one or more LegalChunks.

    Short sections become a single chunk (chunk_index=0, chunk_count=1).
    Long sections are split on lettered subsections and packed to size.
    All chunks share the parent citation/heading/source_url for traceability.
    """
    body = section.text.strip()
    overhead = len(_format_section_chunk_text(section, ""))
    # Floor the body budgets so a very long heading can't collapse packing
    # into uselessly tiny pieces.
    body_target = max(500, target_chars - overhead)
    body_hard_max = max(1000, hard_max_chars - overhead)

    if len(body) <= body_target:
        # Small enough to embed whole — no subsection splitting needed.
        bodies = [body]
    else:
        blocks = _split_subsections(body)
        bodies = _pack_blocks(blocks, body_target, body_hard_max)

    chunk_count = len(bodies)
    chunks: list[LegalChunk] = []
    for index, chunk_body in enumerate(bodies):
        chunks.append(
            LegalChunk(
                # Stable id for Chroma upserts / re-embeds: citation + index.
                chunk_id=f"{section.citation}#{index}",
                source_type=section.source_type,
                citation=section.citation,
                heading=section.heading,
                text=_format_section_chunk_text(section, chunk_body),
                source_url=section.source_url,
                chunk_index=index,
                chunk_count=chunk_count,
            )
        )
    return chunks


def _decision_chunk_id_stem(decision: HearingDecision) -> str:
    """Stable unique stem when the same case_id appears on multiple PDFs.

    MediaSearch sometimes lists corrected / alternate PDFs under one case
    number. Chroma ids must be unique, so include a short source-url token.
    """
    match = re.search(r"/([0-9a-f]{32})\.pdf", decision.source_url, re.IGNORECASE)
    if match:
        token = match.group(1)[:8]
    else:
        token = hashlib.sha1(decision.source_url.encode("utf-8")).hexdigest()[:8]
    return f"{decision.citation}#{token}"


def chunk_decision(
    decision: HearingDecision,
    *,
    target_chars: int = TARGET_CHARS,
    hard_max_chars: int = HARD_MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[LegalChunk]:
    """Turn one HearingDecision into overlapping prose LegalChunks.

    Decisions lack lettered subsection structure, so we pack paragraphs and
    overlap consecutive chunks. Heading on the chunk is the LEA name (stable
    and more useful for retrieval than the caption party line).
    """
    body = decision.text.strip()
    overhead = len(_format_decision_chunk_text(decision, ""))
    body_target = max(500, target_chars - overhead)
    body_hard_max = max(1000, hard_max_chars - overhead)

    if len(body) <= body_target:
        bodies = [body]
    else:
        blocks = _split_paragraphs(body)
        packed = _pack_blocks(blocks, body_target, body_hard_max)
        bodies = _apply_overlap(packed, overlap_chars, body_hard_max)

    chunk_count = len(bodies)
    id_stem = _decision_chunk_id_stem(decision)
    chunks: list[LegalChunk] = []
    for index, chunk_body in enumerate(bodies):
        chunks.append(
            LegalChunk(
                chunk_id=f"{id_stem}#{index}",
                source_type="decision",
                citation=decision.citation,
                heading=decision.lea,
                text=_format_decision_chunk_text(decision, chunk_body),
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
    """Chunk every federal section in order; statute then CFR when concatenated."""
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
    """Load cached sources, chunk them, and write `chunks.json`.

    Expects federal fetchers and ``ingest.oah.fetch`` to have populated
    processed JSON caches.
    """
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
    multi = [c for c in all_chunks if c.chunk_count > 1]
    print(f"Wrote {len(all_chunks)} chunks -> {CHUNKS_PATH}")
    print(f"  statute: {statute_n}  cfr: {cfr_n}  decision: {decision_n}")
    print(f"  sources split into multiple chunks: {len({c.citation for c in multi})}")

    sample = [c for c in all_chunks if c.citation == "20 U.S.C. § 1415"]
    if sample:
        print(f"  example 20 U.S.C. § 1415 -> {sample[0].chunk_count} chunks")
        print(f"    chunk 0 preview ({len(sample[0].text)} chars):")
        print("   ", sample[0].text[:200].replace("\n", " ") + "...")

    oah_sample = [c for c in all_chunks if c.citation == "OAH 2025080622"]
    if oah_sample:
        print(
            f"  example {oah_sample[0].citation} -> {oah_sample[0].chunk_count} "
            f"chunks (overlap={OVERLAP_CHARS})"
        )
        print(f"    chunk 0 preview ({len(oah_sample[0].text)} chars):")
        print("   ", oah_sample[0].text[:200].replace("\n", " ") + "...")
        if len(oah_sample) > 1:
            # Show that chunk 1 starts with a tail from chunk 0's body.
            c0_body = oah_sample[0].text.split("\n\n", 1)[-1]
            c1_body = oah_sample[1].text.split("\n\n", 1)[-1]
            tail = _overlap_tail(c0_body, OVERLAP_CHARS)
            overlapped = bool(tail and c1_body.startswith(tail[:80]))
            print(f"    chunk 1 starts with overlap from chunk 0: {overlapped}")
