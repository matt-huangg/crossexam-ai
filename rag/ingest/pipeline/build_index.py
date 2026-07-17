"""Build a local Chroma index from processed LegalChunk records.

This is the last offline step of the ingest pipeline:

  fetch_*  →  section/decision JSON  →  chunk.py  →  chunks.json  →  build_index.py
                                                                     ↓
                                                            rag/index/chroma/ (Chroma)

Why local Chroma for now:

  - The corpus is bounded and static — no need for a managed vector DB while
    we validate retrieval quality.
  - Chroma's DefaultEmbeddingFunction runs a local ONNX MiniLM model, so
    we can develop without AWS/Bedrock credentials.
  - Production can later swap the embedding function (e.g. Bedrock Titan)
    and/or ship the persisted index to S3; the chunk + metadata shape stays
    the same.

Re-running this script rebuilds the collection from scratch (delete +
recreate) so chunk_id upserts don't leave stale vectors after a re-chunk.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from ingest.cache import PROCESSED_DIR, load_models
from ingest.models import LegalChunk

CHUNKS_PATH = PROCESSED_DIR / "chunks.json"

# pipeline/ -> ingest/ -> rag/
RAG_DIR = Path(__file__).resolve().parents[2]
# Top-level index folder (gitignored except .gitkeep).
INDEX_DIR = RAG_DIR / "index"
# Chroma PersistentClient writes sqlite + segment files here — keep it separate
# from INDEX_DIR root so other index artifacts (manifests, exports) can coexist.
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"

COLLECTION_NAME = "legal_corpus"

# Smoke-test queries: federal passages + an OAH practice-style query.
SMOKE_QUERIES = [
    "prior written notice content requirements",
    "procedural safeguards due process hearing",
    "IEP implementation failure to provide services",
]


def load_chunks(path: Path = CHUNKS_PATH) -> list[LegalChunk]:
    """Load chunked LegalChunk records written by chunk.py."""
    chunks = load_models(path, LegalChunk)
    if chunks is None:
        raise FileNotFoundError(
            f"Missing {path}. Run `python -m ingest.pipeline.chunk` first "
            "(after federal fetchers) to produce chunks.json."
        )
    return chunks


def get_client(persist_dir: Path = CHROMA_PERSIST_DIR) -> chromadb.ClientAPI:
    """Open (or create) the on-disk Chroma store at `persist_dir`.

    Default location: ``rag/index/chroma/`` (CHROMA_PERSIST_DIR). PersistentClient
    writes chroma.sqlite3 and vector segment subdirs there so the index survives
    process restarts — unlike the ephemeral EphemeralClient.
    """
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def rebuild_collection(
    chunks: list[LegalChunk],
    *,
    client: chromadb.ClientAPI | None = None,
) -> Collection:
    """Replace the legal_corpus collection with embeddings for `chunks`.

    Deletes any existing collection first so a re-chunk (different chunk_ids
    or text) cannot leave orphan vectors behind. Also drops the legacy
    ``federal_law`` name if present from earlier builds.
    """
    client = client or get_client()

    # Drop the old collection if present. get_collection raises if missing,
    # so we probe via list_collections instead of try/except on every rebuild.
    existing = {c.name for c in client.list_collections()}
    for name in (COLLECTION_NAME, "federal_law"):
        if name in existing:
            client.delete_collection(name)

    # DefaultEmbeddingFunction = local ONNX all-MiniLM-L6-v2. First run may
    # download the model weights; after that it's fully offline.
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": (
                "IDEA statute (20 U.S.C. Ch. 33) + 34 CFR Part 300 + "
                "CA OAH special-education decisions"
            )
        },
    )

    ids = [chunk.chunk_id for chunk in chunks]
    documents = [chunk.text for chunk in chunks]
    # Chroma metadata values must be str | int | float | bool — no None.
    metadatas = [
        {
            "source_type": chunk.source_type,
            "citation": chunk.citation,
            "heading": chunk.heading,
            "source_url": chunk.source_url,
            "chunk_index": chunk.chunk_index,
            "chunk_count": chunk.chunk_count,
            "case_id": chunk.case_id,
            "lea": chunk.lea,
            "decision_date": chunk.decision_date,
        }
        for chunk in chunks
    ]

    # Batch upsert keeps memory bounded if the corpus grows (decisions later).
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    return collection


def query_collection(
    collection: Collection,
    query: str,
    *,
    n_results: int = 3,
    source_type: str | None = None,
) -> dict:
    """Run a similarity search, optionally filtered by ``source_type``.

    `source_type` filter lets persona nodes scope retrieval later
    (``statute`` / ``cfr`` / ``decision``); filtering is optional.
    """
    where = {"source_type": source_type} if source_type else None
    return collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
    )


def main() -> Collection:
    """Load chunks, rebuild the local Chroma index, return the collection."""
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_PATH}")
    collection = rebuild_collection(chunks)
    print(
        f"Indexed {collection.count()} vectors into "
        f"{CHROMA_PERSIST_DIR} (collection={COLLECTION_NAME!r})"
    )
    return collection


if __name__ == "__main__":
    coll = main()
    print("\nSmoke-test queries:")
    for q in SMOKE_QUERIES:
        result = query_collection(coll, q, n_results=3)
        print(f"\n  Q: {q}")
        # Chroma returns lists-of-lists (one inner list per query).
        for citation, doc, distance in zip(
            result["metadatas"][0],
            result["documents"][0],
            result["distances"][0],
            strict=True,
        ):
            preview = doc.replace("\n", " ")[:120]
            print(f"    [{distance:.3f}] {citation['citation']}: {preview}...")
