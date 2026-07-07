# rag

Corpus ingestion and local embedding pipeline for the three corpora described
in `../ARCHITECTURE.md`:

- IDEA statute + 34 CFR Part 300 (federal, public domain)
- Published due process hearing decisions from a state Office of
  Administrative Hearings (public record)
- Per-session case file handling (synthetic/hypothetical only — see the
  "No real case data, ever" constraint in `../README.md`)

Embeddings are stored locally (FAISS or Chroma — TBD) rather than in a
managed vector DB, since this corpus is bounded and static.

Not yet implemented. See `../ARCHITECTURE.md` for the RAG pipeline design and
`../ROADMAP.md` for sequencing.
