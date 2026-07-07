# CrossExam AI

An AI-powered practice tool for attorneys to rehearse **cross-examining a
hostile witness** ahead of a special education due process hearing (IDEA).

> **This is a rehearsal tool, not legal advice.** CrossExam AI does not
> generate legal strategy, does not review or advise on real cases, and does
> not substitute for attorney judgment. It exists solely so attorneys can
> practice the mechanics of cross-examination against a realistic, grounded
> simulation before the real hearing.

## What this is

The user practices live cross-examination against an AI-played adverse
witness. An AI opposing counsel raises objections, and an AI hearing officer
rules on them — all grounded in real IDEA statute, federal regulations, and
published state due process hearing decisions, rather than generic AI
improvisation.

## Why it exists

Preparing for a due process hearing means rehearsing cross-examination — a
skill that's hard to practice alone and expensive to schedule with a colleague
on demand. CrossExam AI gives attorneys an always-available, realistic
sparring partner grounded in real procedural and legal standards.

## Current scope (MVP)

**Single skill, single witness.** The MVP is a focused drill: cross-examining
one hostile witness in one session, not a full multi-witness hearing
simulation. See [`ROADMAP.md`](./ROADMAP.md) for what comes after.

## How it works

1. You ask the witness a question.
2. The witness answers — adversarial but fact-consistent with the session's
   case file, and resistant to leading questions (it doesn't just fold).
3. Opposing counsel may object on realistic cross-exam grounds (e.g.
   argumentative, asked-and-answered, compound, non-responsive).
4. If there's an objection, the hearing officer rules — sustained or
   overruled — based on real procedural standards.
5. This loops until you end questioning, at which point you get a structured
   debrief on your question technique and objection outcomes.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full state machine and RAG
design.

## Core architecture at a glance

- **RAG**: every persona is grounded in real material, not vibes — IDEA
  statute + 34 CFR Part 300, published due process hearing decisions from a
  state Office of Administrative Hearings, and a per-session synthetic case
  file. Corpus is embedded locally (FAISS/Chroma) rather than a managed
  vector DB, since it's bounded and static.
- **LangGraph**: orchestrates the drill as an explicit state machine, chosen
  over Strands/CrewAI because this domain needs procedural control, not just
  model-driven improvisation.
- **Amazon Bedrock AgentCore**: production hosting/infra — Runtime
  (Firecracker microVM per session), Memory (evidentiary transcript
  persistence), and Observability (session traces double as reviewable
  transcripts). Model is Claude via Amazon Bedrock.
- **Frontend**: Next.js static export (SPA) on S3 + CloudFront, talking to a
  backend proxy Lambda that holds AWS credentials and signs requests to
  AgentCore Runtime.

## Repository structure

```
crossexam-ai/
├── frontend/   # Next.js static-export app
├── backend/    # LangGraph agent, deployed to AgentCore Runtime
├── rag/        # Corpus ingestion (statute, regs, case decisions) + embedding pipeline
├── infra/      # S3 / CloudFront / Lambda deployment config
└── docs/       # Architecture notes, case file schema, persona design
```

## Critical constraints

- **No real case data, ever.** All case files used in development or demos
  are entirely synthetic/hypothetical. This project must never contain real
  client information, given attorney-client privilege and confidentiality
  obligations.
- **Legal accuracy grounding is a hard requirement.** The hearing officer's
  rulings and opposing counsel's objections must be traceable to retrieved
  statute/regulation/decision text, not freeform model reasoning.
- **The witness must not be an easy "yes machine."** Realistic resistance to
  leading questions is the entire point of the training value.
- **Cost-consciousness**: local/embedded solutions are preferred over managed
  services with non-usage-based minimum costs (e.g. no OpenSearch
  Serverless; be aware AgentCore Runtime memory bills for idle session time).

## Documentation

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — LangGraph state machine, persona
  design, RAG pipeline
- [`ROADMAP.md`](./ROADMAP.md) — MVP → voice → full multi-witness hearing
  simulation
- [`docs/`](./docs) — case file schema, persona design notes

## Status

Early development. Architecture and scope are defined; implementation is in
progress.
