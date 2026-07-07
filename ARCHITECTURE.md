# Architecture

This document expands on the LangGraph state machine and the RAG pipeline
that grounds it. For product scope and constraints, see [`README.md`](./README.md).

## 1. Drill state machine (LangGraph)

The drill is modeled as an explicit state machine rather than a
model-driven agentic loop, because the domain requires procedural control:
objections must be evaluated and ruled on deterministically as discrete
turns, not improvised as free text by a single model call.

```
                 ┌────────────────────────────────────────────┐
                 │                                              │
                 ▼                                              │
        [ Ask question ]                                        │
                 │                                               │
                 ▼                                               │
        [ Witness answers ]                                      │
                 │                                               │
                 ▼                                               │
        [ Opposing counsel: objection? ]                         │
           │                    │                                │
     no objection          objection raised                      │
           │                    │                                │
           │                    ▼                                │
           │      [ Hearing officer rules: sustained / overruled ]
           │                    │                                │
           │                    └──────────── loop back ─────────┘
           ▼
   (attorney ends questioning?)
           │
          yes
           ▼
   [ Debrief / feedback report ]
```

- **Sustained** objections typically require the attorney to rephrase or
  withdraw the question before the witness answers it; the graph loops back
  to `Ask question` rather than proceeding to an answer.
- **Overruled** objections send the flow back to `Witness answers` for the
  original question.
- The loop continues until the attorney explicitly ends questioning, which
  transitions to `Debrief`.

### Nodes / personas

Each persona is a separate LangGraph node with its own system prompt and its
own retrieval scope. They are kept separate (rather than one model
role-playing all three) so each can be grounded, tested, and tuned
independently, and so objections/rulings can be traced to retrieved sources
distinct from the witness's case-file grounding.

| Node | Role | Retrieval scope | Key behavioral requirement |
|---|---|---|---|
| **Witness** | Adversarial but fact-consistent hostile witness | Per-session case file only (facts, role, exhibits) | Must resist leading questions realistically — must not fold to every question. This is the single most important behavior in the system; an over-compliant witness defeats the entire training purpose. |
| **Opposing counsel** | Objects on realistic cross-exam grounds | IDEA statute/regs + due process decisions (objection standards) | Objects on argumentative, asked-and-answered, compound, non-responsive, etc. — **never** "leading," since leading questions are permitted on cross-examination. Must not object reflexively on every turn; objection frequency should reflect real practice. |
| **Hearing officer** | Neutral ruling authority | IDEA statute/regs + due process decisions (procedural standards) | Rulings must be traceable to retrieved statute/regulation/decision text, not freeform reasoning. Neutral — does not favor either side. |
| **Debrief** | Post-drill structured feedback | Full session transcript (via Memory) | Produces structured feedback on question technique (leading vs. open, compound questions, control of witness) and objection outcomes — not generic praise. |

### Why LangGraph over Strands/CrewAI

Cross-examination has real procedural rules: an objection must be ruled on
before the witness may answer (or must not answer, if sustained); the
hearing officer is not "just another chat participant," it's a gate in the
flow. LangGraph's explicit graph/state model lets us encode this control
flow directly, rather than relying on multi-agent frameworks whose routing
is itself model-driven.

## 2. RAG pipeline

Three distinct corpora feed the system, each serving a different persona
and grounding a different kind of output:

| Corpus | Grounds | Notes |
|---|---|---|
| IDEA statute + 34 CFR Part 300 | Hearing officer rulings, opposing counsel objection standards | Federal, public domain. Static — re-ingested only on regulatory change. |
| Published due process hearing decisions (one state's Office of Administrative Hearings) | Hearing officer rulings, opposing counsel objections, precedent | Public record. Bounded corpus tied to a single state's OAH for the MVP. |
| Per-session case file (facts, witness role, exhibits) | Witness answers | Synthetic/hypothetical only — see constraint on real case data in `README.md`. Scoped per session, not shared across sessions. |

### Ingestion (`rag/`)

- Source documents (statute text, CFR text, decision PDFs/text) are chunked
  and embedded, then persisted to a local vector store (FAISS or Chroma —
  see open question below).
- Because the statutory/regulatory/decision corpus is bounded and static,
  it is embedded **once, offline**, and the resulting index is shipped/
  loaded by the backend at startup or session init — not re-embedded per
  session.
- The per-session case file is small enough to be embedded (or simply
  included in-context, if small enough to skip retrieval entirely) at
  session start, and is discarded/archived with the session — it is never
  merged into the shared static corpus.

### Retrieval at inference time

- Each persona node queries only its own retrieval scope (table above) —
  the witness node never retrieves objection/procedural standards, and the
  hearing officer/opposing counsel nodes never retrieve the case file
  directly (they see it only via the transcript, same as a real hearing
  officer would).
- Retrieved passages are passed into the persona's prompt as cited context,
  so rulings and objections can be traced back to a specific
  statute/regulation/decision excerpt — this traceability is a hard
  requirement, not a nice-to-have (see `README.md` constraints).

### Cost-conscious choice: local embeddings over managed vector DB

The statute/regs/decisions corpus is bounded and effectively static, so a
managed, always-on vector service (e.g. Amazon OpenSearch Serverless) is not
justified — it has a real non-trivial minimum monthly cost regardless of
usage. Embedding locally with FAISS or Chroma, loaded into the AgentCore
Runtime session, avoids that fixed cost entirely and fits a corpus this size.

## 3. Production infrastructure (Amazon Bedrock AgentCore)

- **Runtime**: hosts the LangGraph app, one Firecracker microVM per session
  — provides session isolation without the operational overhead of managing
  that isolation directly.
- **Memory**: persists the evidentiary record/transcript within a session
  (so the hearing officer/opposing counsel can catch a witness contradicting
  an earlier answer) and across sessions (so an attorney can resume
  cross-exam prep across multiple days on the same case file).
- **Observability**: session traces are treated as a first-class product
  artifact — a reviewable transcript of the drill — not merely a debugging
  tool for developers.
- **Model**: Claude via Amazon Bedrock, used by all four persona nodes
  (model choice/version per persona is an implementation detail, not fixed
  here).

**Cost awareness**: AgentCore Runtime Memory bills for idle session time,
not just active processing — session lifecycle (when a session is
considered "ended" vs. "resumable") should be designed deliberately rather
than left open-ended.

## 4. Frontend / hosting

- **Next.js, static export** (`output: 'export'`): a client-side SPA. No
  SSR or Next.js API routes are used, because the actual dynamic work
  (AgentCore calls, streaming, and eventually voice) happens in a separate
  backend proxy, not in Next.js server code.
- **Hosting**: S3 + CloudFront. Chosen over Vercel/Amplify specifically
  because there's no SSR/streaming dependency on the hosting layer itself —
  streaming happens client-side via direct calls to the backend proxy — so
  S3's static-only limitation doesn't apply.
- **Backend proxy**: a Lambda (or similar) holds AWS credentials, signs
  SigV4 requests to AgentCore Runtime, and streams responses back to the
  browser. This is required because the browser can never hold AWS
  credentials directly.

```
Browser (Next.js static SPA)
   │  (no AWS creds)
   ▼
Backend proxy (Lambda) ── holds AWS credentials, signs SigV4
   │
   ▼
Amazon Bedrock AgentCore Runtime (LangGraph app, per-session microVM)
   │
   ▼
Claude (Amazon Bedrock)
```

## 5. Open implementation questions

These are intentionally left open pending further decisions — flagged here
rather than guessed at silently:

- **Vector store**: FAISS vs. Chroma for the local embedding store — not
  yet finalized.
- **State OAH**: which state's Office of Administrative Hearings decisions
  form the precedent corpus for the MVP — not yet finalized.
- **Embedding model**: which embedding model for the RAG corpus (e.g. a
  Bedrock embedding model vs. another provider) — not yet finalized.
- **Session lifecycle**: precise rules for when an AgentCore Memory session
  is archived/ended vs. kept resumable, given idle-time billing.
