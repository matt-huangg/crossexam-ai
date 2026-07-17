# California OAH decision corpus (MVP scope)

Published IDEA due process hearing decisions that ground the hearing
officer and opposing counsel personas with practice/precedent text —
alongside federal statute + 34 CFR Part 300.

This is **Corpus 2** in [`../ARCHITECTURE.md`](../ARCHITECTURE.md). It is
public-record administrative decisions, not real client case files.

## Locked choices

| Choice | Decision |
|---|---|
| State | California |
| Forum | Office of Administrative Hearings (OAH), Special Education Division |
| Geography | **Statewide** CA OAH (LEA kept as metadata for optional slicing) |
| Time range (MVP) | Last ~**5 years** (case-number year prefix on listing filenames) |
| Expand later | Full OAH searchable set **2013 → present** |
| Source of truth | Official OAH PDFs only (not third-party aggregators) |
| Document type | Prefer decisions **after hearing** (AccMod-ish listing heuristic for MVP) |

## What we intentionally skip (for now)

- **Decisions by settlement** — negotiated outcomes; weak as “how officers rule”
  (filename heuristic is imperfect; body checks can tighten this later)
- **Generic orders** (scheduling, etc.) — low value for rehearsal grounding
- **CDE SEAHD 1993–2005** — different era/format; optional later
- **~2005–2012 gap** — not cleanly on the current OAH search DB; skip for MVP
- **LLM extraction/summaries as corpus text** — deterministic PDF text only;
  optional LLM tags later must not replace cited passages

## Official sources

1. **Search / browse (primary docs page)**  
   https://www.dgs.ca.gov/OAH/Case-Types/Special-Education/Services/Page-Content/Special-Education-Services-List-Folder/Search-Special-Education-Decisions-and-Orders  
   - OAH states the searchable decisions DB covers decisions after hearing
     **since 2013** (excluding some PII-heavy decisions).

2. **Decisions listing / PDF paths**  
   https://www.dgs.ca.gov/en/OAH/Case-Types/Special-Education/Services/Decisions  
   - MediaSearch currently serves UUID media URLs; display filenames carry
     the OAH case number (e.g. `2025080622 AccMod.pdf`).

3. **Box.com bulk dump** (when site search is flaky)  
   https://dgscloud.box.com/s/05yxfqlaa08743v0kic30pmvzphsys2i

4. **Older archive (not MVP)** — CDE SEAHD 1993–2005  
   https://www2.cde.ca.gov/seho/

5. **Ongoing refresh later** — OAH ListServe (monthly new decisions)

## LEA metadata

There is no city-specific due process tribunal. District names appear in
statewide OAH captions. Ingest parses `lea` onto each `HearingDecision`
but does **not** hard-filter to one district. Optional `lea_filters` on
`ingest.oah.fetch.main` can slice later if needed.

## Ingestion rules

- Fetch official PDFs → extract text with **deterministic** tools
  (`pymupdf` / similar) → chunk → embed into local Chroma.
- Preserve `source_url`, OAH case number, LEA, and decision date in
  metadata for traceability.
- Do **not** embed LLM-written summaries as the authoritative passage;
  retrieve and cite exact extracted text.

## Implementation entry points

| Module | Responsibility |
|---|---|
| [`oah/discovery.py`](../rag/ingest/oah/discovery.py) | MediaSearch PDF listing |
| [`oah/pdf.py`](../rag/ingest/oah/pdf.py) | Download + pymupdf extract |
| [`oah/parse.py`](../rag/ingest/oah/parse.py) | `HearingDecision` (+ optional LEA helpers) |
| [`oah/fetch.py`](../rag/ingest/oah/fetch.py) | Orchestrate + cache |

Pipeline target (same shape as federal law):

```
fetch PDFs → data/raw/decisions/ → HearingDecision JSON → chunk → Chroma
```
