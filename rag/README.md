# rag

Corpus ingestion and local embedding pipeline for the three corpora described
in `../ARCHITECTURE.md`:

- IDEA statute + 34 CFR Part 300 (federal, public domain) — ingest + local
  Chroma index under `ingest/federal/` + `ingest/pipeline/`
- Published due process hearing decisions from California OAH (public
  record) — under `ingest/oah/` (see `../docs/oah-decision-corpus.md`)
- Per-session case file handling (synthetic/hypothetical only — see the
  "No real case data, ever" constraint in `../README.md`)

Embeddings for the federal-law corpus are stored locally in Chroma under
`index/chroma/` (gitignored). Production may later swap the embedding
model (e.g. Bedrock Titan) and/or ship the index to S3.

## Rebuild federal-law index

```bash
cd rag
uv run python -m ingest.federal.fetch_statute
uv run python -m ingest.federal.fetch_cfr
uv run python -m ingest.pipeline.chunk
uv run python -m ingest.pipeline.build_index
```

## OAH decisions

```bash
cd rag
uv run python -m ingest.oah.fetch
```

See `ingest/README.md` for package layout, `../ARCHITECTURE.md` for RAG
design, and `../ROADMAP.md` for sequencing.
