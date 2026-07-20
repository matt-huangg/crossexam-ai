"""Build a local Chroma index from processed LegalChunk records.

Last offline step of the ingest pipeline:

  fetch_*  ->  section/decision JSON  ->  chunk.py  ->  chunks.json  ->  build_index.py
                                                                          |
                                                                          v
                                                                 rag/index/chroma/ (Chroma)

Why local Chroma + a local embedding model for now (see ../../ARCHITECTURE.md):
  - The corpus is bounded and static - no need for a managed vector DB yet.
  - Chroma's DefaultEmbeddingFunction runs a local ONNX MiniLM model, so we
    can develop without AWS/Bedrock credentials. Production can swap in a
    Bedrock embedding model later - the chunk + metadata shape stays the same.
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
INDEX_DIR = RAG_DIR / "index"
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"

COLLECTION_NAME = "legal_corpus"

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
            f"Missing {path}. Run `python -m ingest.pipeline.chunk` first."
        )
    return chunks


def get_client(persist_dir: Path = CHROMA_PERSIST_DIR) -> chromadb.ClientAPI:
    """Open (or create) the on-disk Chroma store at `persist_dir`.

    PersistentClient writes sqlite + vector segments to disk so the index
    survives process restarts — unlike EphemeralClient (in-memory only).
    """
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def rebuild_collection(
    chunks: list[LegalChunk],
    *,
    client: chromadb.ClientAPI | None = None,
) -> Collection:
    """Replace the `legal_corpus` collection with embeddings for `chunks`.

    Deletes any existing collection first so a re-chunk (different chunk_ids
    or text) cannot leave orphan vectors behind. Chroma embeds `documents`
    automatically via DefaultEmbeddingFunction (local ONNX MiniLM).
    """
    client = client or get_client()

    # Drop old collections if present. list_collections avoids try/except on
    # get_collection for the missing-name case.
    existing = {c.name for c in client.list_collections()}
    for name in (COLLECTION_NAME, "federal_law"):
        if name in existing:
            client.delete_collection(name)

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

    # Batch so embedding ~10k chunks doesn't hold everything in one call.
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
    """Run a similarity search, optionally filtered by `source_type`.

    `source_type` lets persona nodes scope retrieval later
    (statute / cfr / decision); filtering is optional.
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
        for citation, doc, distance in zip(
            result["metadatas"][0],
            result["documents"][0],
            result["distances"][0],
            strict=True,
        ):
            preview = doc.replace("\n", " ")[:120]
            print(f"    [{distance:.3f}] {citation['citation']}: {preview}...")
