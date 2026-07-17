# Roadmap

Sequencing from MVP through voice support to a full multi-witness hearing
simulation. See [`README.md`](./README.md) for scope framing and
[`ARCHITECTURE.md`](./ARCHITECTURE.md) for technical design.

## Phase 0 — Foundations (pre-MVP)

Groundwork that everything else depends on.

- [x] Finalize which state's Office of Administrative Hearings supplies the
      published due process decision corpus.
      → California OAH; San Diego–focused MVP slice. See
      [`docs/oah-decision-corpus.md`](./docs/oah-decision-corpus.md).
- [ ] Define the synthetic case file schema (facts, witness role, exhibits)
      — see `docs/`. No real case data at any point, including here.
- [x] Ingest and embed IDEA statute + 34 CFR Part 300 (`rag/`).
- [ ] Ingest and embed the chosen state's published due process decisions
      (`rag/ingest/oah/`).
- [ ] Build 1–2 fully synthetic demo case files for development/testing.
- [ ] Stand up the LangGraph state machine skeleton (`backend/`) with the
      four persona nodes as stubs (no retrieval yet).

## Phase 1 — MVP: single skill, single witness

The core rehearsal loop, text-only, one witness, one skill.

- [ ] Wire the witness node to per-session case-file retrieval; validate it
      resists leading questions rather than folding (this is the key
      behavioral bar for the entire product — should be explicitly tested,
      not just eyeballed).
- [ ] Wire opposing counsel node to statute/regs/decisions retrieval for
      objection grounds (argumentative, asked-and-answered, compound,
      non-responsive).
- [ ] Wire hearing officer node to the same corpus for rulings; verify
      rulings are traceable to specific retrieved passages.
- [ ] Implement the objection/ruling loop-back logic (sustained → rephrase,
      overruled → witness answers) as explicit graph edges.
- [ ] Implement debrief node: structured feedback on question technique and
      objection outcomes at end of session.
- [ ] Deploy the LangGraph app to Amazon Bedrock AgentCore Runtime.
- [ ] Wire AgentCore Memory for within-session transcript persistence
      (contradiction-catching depends on this).
- [ ] Build the Next.js static-export frontend: single-drill UI (ask
      question → see answer/objection/ruling → end session → see debrief).
- [ ] Build the backend proxy Lambda (SigV4 signing, streaming passthrough).
- [ ] Deploy frontend to S3 + CloudFront.
- [ ] In-app and README disclosure: rehearsal tool, not legal advice.
- [ ] Basic session review: read back a past transcript.

**Exit criteria for MVP**: an attorney can run a full cross-examination
drill against one synthetic hostile witness end-to-end, get realistic
objections/rulings grounded in real sources, and receive a debrief — with no
real case data ever touching the system.

## Phase 2 — Cross-session persistence & review

- [ ] Cross-session Memory: resume prep on the same case file across
      multiple days.
- [ ] Contradiction detection: surface when a witness's current answer
      conflicts with an earlier one in the same or a prior session.
- [ ] Session history/list view in the frontend.
- [ ] Treat AgentCore Observability traces as user-facing reviewable
      transcripts, not just developer debugging output.
- [ ] Explicit session lifecycle policy (archive/end vs. resumable) to
      manage AgentCore Memory idle-time cost.

## Phase 3 — Voice

- [ ] Browser speech-to-text for attorney question input.
- [ ] Distinct text-to-speech voices per persona (witness / opposing
      counsel / hearing officer) — Amazon Polly or Web Speech API.
- [ ] Objections that audibly interrupt the witness's answer mid-sentence,
      for realism.
- [ ] Latency/streaming tuning so voice interruptions feel real-time rather
      than turn-based.

## Phase 4 — Multi-witness hearing simulation

The larger evolution beyond the single-witness drill.

- [ ] Support multiple witnesses per case file, examined in sequence.
- [ ] Direct examination practice (in addition to cross), if in scope.
- [ ] Exhibit handling: introducing/moving exhibits into evidence, objections
      to exhibits.
- [ ] Full-hearing debrief across all witnesses, not just per-witness.
- [ ] Re-evaluate case-file schema and Memory design for multi-witness
      scale (per-witness fact consistency, cross-witness contradiction
      checks).

## Explicitly out of scope (for now)

- Legal strategy generation or case advice of any kind.
- Real case data or client information, at any phase.
- Full hearing simulation beyond a single witness, before Phase 4.
