# ingest

Corpus ingestion package. Run modules from the `rag/` directory:

```bash
cd rag
uv run python -m ingest.federal.fetch_statute
uv run python -m ingest.federal.fetch_cfr
uv run python -m ingest.pipeline.chunk
uv run python -m ingest.pipeline.build_index
uv run python -m ingest.oah.fetch
```

```
ingest/
  models.py    # LegalSection, LegalChunk, HearingDecision
  cache.py     # data/raw + data/processed helpers
  federal/     # statute + CFR fetchers
  oah/         # CA OAH decisions (discovery, pdf, parse, fetch)
  pipeline/    # chunk + Chroma index
```
