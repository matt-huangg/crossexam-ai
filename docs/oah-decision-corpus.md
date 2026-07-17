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
| Geography (MVP) | Prefer **San Diego Unified** (+ nearby LEAs if the set is thin: Grossmont, Poway, Sweetwater) |
| Time range (MVP) | Last ~**5 years** |
| Expand later | Full OAH searchable set **2013 → present**, then statewide if needed |
| Source of truth | Official OAH PDFs only (not third-party aggregators) |
| Document type | Decisions **after hearing** (full ALJ written decisions) |

## What we intentionally skip (for now)

- **Decisions by settlement** — negotiated outcomes; weak as “how officers rule”
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
   - PDFs under paths like  
     `/media/Divisions/OAH/Special-Education/SE-Decisions/{year}/.../*.pdf`

3. **Box.com bulk dump** (when site search is flaky)  
   https://dgscloud.box.com/s/05yxfqlaa08743v0kic30pmvzphsys2i

4. **Older archive (not MVP)** — CDE SEAHD 1993–2005  
   https://www2.cde.ca.gov/seho/

5. **Ongoing refresh later** — OAH ListServe (monthly new decisions)

## San Diego note

There is no separate San Diego due process tribunal. Cases involving San
Diego districts are **statewide OAH** decisions that name those LEAs.
Ingest filters by district string (e.g. `"San Diego Unified"`), it does
not scrape a city-specific portal.

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
| [`oah/parse.py`](../rag/ingest/oah/parse.py) | `HearingDecision` + LEA filter |
| [`oah/fetch.py`](../rag/ingest/oah/fetch.py) | Orchestrate + cache |

Pipeline target (same shape as federal law):

```
fetch PDFs → data/raw/decisions/ → HearingDecision JSON → chunk → Chroma
```
