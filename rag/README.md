# rag

Corpus ingestion and local embedding pipeline for the three corpora described
in `../ARCHITECTURE.md`:

- IDEA statute + 34 CFR Part 300 (federal, public domain) — **ingest + local
  Chroma index working** (`ingest/fetch_*.py`, `chunk.py`, `build_index.py`)
- Published due process hearing decisions from California OAH (public
  record) — **scope locked**, fetcher stubbed (`ingest/fetch_decisions.py`;
  see `../docs/oah-decision-corpus.md`)
- Per-session case file handling (synthetic/hypothetical only — see the
  "No real case data, ever" constraint in `../README.md`)

Embeddings for the federal-law corpus are stored locally in Chroma under
`index/chroma/` (gitignored). Production may later swap the embedding
model (e.g. Bedrock Titan) and/or ship the index to S3.

## Rebuild federal-law index

```bash
cd rag/ingest
uv run python fetch_statute.py   # caches to data/raw + data/processed
uv run python fetch_cfr.py
uv run python chunk.py
uv run python build_index.py     # writes index/chroma, runs smoke queries
```

See `../ARCHITECTURE.md` for RAG design and `../ROADMAP.md` for sequencing.
