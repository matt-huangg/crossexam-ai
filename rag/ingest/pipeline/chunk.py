"""Split LegalSection records into retrieval-sized LegalChunk records.

Why chunk at all:

  Embedding an entire multi-page section (e.g. 20 U.S.C. § 1415 at ~43k
  chars) makes similarity search return a giant blob. Hearing officer /
  opposing counsel prompts need a focused passage they can cite — not the
  whole procedural-safeguards section.

Strategy (deterministic, no LLM):

  1. Prefer legal structure: split on lettered subsections that start a
     line — ``(a)``, ``(b)``, … — so numbered paragraphs ``(1)``, ``(2)``
     stay with their parent letter.
  2. If the whole section fits under TARGET_CHARS, emit one chunk.
  3. Otherwise pack consecutive subsection blocks until TARGET_CHARS,
     starting a new chunk when the next block would overflow.
  4. If a single block still exceeds HARD_MAX_CHARS (rare), split on
     newlines as a last resort.

Every chunk text is prefixed with ``{citation} — {heading}`` so the
embedding itself carries the cite, which improves retrieval and makes
retrieved hits self-describing in the persona prompt.
"""

from __future__ import annotations

import re

from ingest.cache import PROCESSED_DIR, load_processed, save_models
from ingest.models import LegalChunk, LegalSection

STATUTE_PROCESSED_PATH = PROCESSED_DIR / "20-usc-ch33.json"
CFR_PROCESSED_PATH = PROCESSED_DIR / "34-cfr-300.json"
CHUNKS_PATH = PROCESSED_DIR / "chunks.json"

# Soft target (~750–1000 tokens of English prose). We pack subsections up to
# this size so a chunk is useful for retrieval without being a whole chapter.
TARGET_CHARS = 3500
# Absolute ceiling after forced newline splits. Embedding models and prompt
# budgets both hate multi-page blobs; this is the "never go past here" guard.
HARD_MAX_CHARS = 6000

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


def _split_oversized(block: str, max_chars: int) -> list[str]:
    """Last-resort split on newlines when one subsection exceeds HARD_MAX_CHARS.

    Most lettered subsections fit under the hard max. This path only fires for
    unusually long single blocks where we have no finer legal boundary left —
    better a clean line break than a mid-word cut or an unembeddable blob.
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
    """Pack subsection blocks into chunks near target_chars.

    Consecutive ``(a)``/``(b)``/``(c)`` blocks stay together when they fit, so
    retrieval returns a coherent legal unit instead of an orphaned fragment.
    Soft target (not hard) on packing: slightly-over is preferred to leaving a
    tiny leftover subsection alone in a nearly-empty chunk.
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
        # Oversized single subsections are pre-split; normal ones pass through
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


def _format_chunk_text(section: LegalSection, body: str) -> str:
    """Prefix chunk body with citation + heading for embedding and display.

    Putting the cite in the embedded text (not only metadata) helps similarity
    search match queries that mention the section number, and makes retrieved
    hits self-describing when dropped into a persona prompt.
    """
    return f"{section.citation} — {section.heading}\n\n{body.strip()}"


def _prefix_overhead(section: LegalSection) -> int:
    """Chars added by `_format_chunk_text` beyond the body itself.

    Packing must reserve this space so the *final* chunk (prefix + body) stays
    under TARGET_CHARS / HARD_MAX_CHARS, not just the body alone.
    """
    return len(_format_chunk_text(section, ""))


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
    overhead = _prefix_overhead(section)
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
                text=_format_chunk_text(section, chunk_body),
                source_url=section.source_url,
                chunk_index=index,
                chunk_count=chunk_count,
            )
        )
    return chunks


def chunk_sections(sections: list[LegalSection]) -> list[LegalChunk]:
    """Chunk every section in order; statute then CFR when callers concatenate."""
    chunks: list[LegalChunk] = []
    for section in sections:
        chunks.extend(chunk_section(section))
    return chunks


def main() -> list[LegalChunk]:
    """Load cached LegalSections, chunk them, and write `chunks.json`.

    Expects `ingest.federal.fetch_statute` and `ingest.federal.fetch_cfr` to
    have already populated
    the processed JSON caches. Re-run those first if this raises FileNotFoundError.
    """
    statute = load_processed(STATUTE_PROCESSED_PATH)
    cfr = load_processed(CFR_PROCESSED_PATH)
    if statute is None or cfr is None:
        missing = []
        if statute is None:
            missing.append(str(STATUTE_PROCESSED_PATH))
        if cfr is None:
            missing.append(str(CFR_PROCESSED_PATH))
        raise FileNotFoundError(
            "Missing processed section cache. Run "
            "`python -m ingest.federal.fetch_statute` and "
            f"`python -m ingest.federal.fetch_cfr` first. Missing: {', '.join(missing)}"
        )

    chunks = chunk_sections(statute + cfr)
    save_models(CHUNKS_PATH, chunks)
    return chunks


if __name__ == "__main__":
    all_chunks = main()
    statute_n = sum(1 for c in all_chunks if c.source_type == "statute")
    cfr_n = sum(1 for c in all_chunks if c.source_type == "cfr")
    multi = [c for c in all_chunks if c.chunk_count > 1]
    print(f"Wrote {len(all_chunks)} chunks -> {CHUNKS_PATH}")
    print(f"  statute: {statute_n}  cfr: {cfr_n}")
    print(f"  sections split into multiple chunks: {len({c.citation for c in multi})}")
    # Smoke-check a known long section so a broken splitter is obvious in CLI output.
    sample = [c for c in all_chunks if c.citation == "20 U.S.C. § 1415"]
    if sample:
        print(f"  example 20 U.S.C. § 1415 -> {sample[0].chunk_count} chunks")
        print(f"    chunk 0 preview ({len(sample[0].text)} chars):")
        print("   ", sample[0].text[:200].replace("\n", " ") + "...")
