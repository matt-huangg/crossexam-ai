# backend

The LangGraph agent that runs the cross-examination drill, deployed later to
Amazon Bedrock AgentCore Runtime.

Contains the four persona nodes (witness, opposing counsel, hearing officer,
debrief) and the state machine wiring described in `../ARCHITECTURE.md`.

## Setup

```bash
cd backend
uv sync
```

## Step status

**Step 1 — done:** shared drill state — [`graph/state.py`](graph/state.py)
(`DrillState`).

**Step 2 — done:** one hard-coded witness stub + tiny graph
`START → witness → END` — [`graph/nodes/witness.py`](graph/nodes/witness.py),
[`graph/build.py`](graph/build.py).

**Not yet:** opposing counsel / hearing officer / debrief, conditional edges,
LLM calls, Chroma retrieval, case files, or AgentCore.

### LangGraph primitives (map to the drill)

| Primitive | Meaning here |
|---|---|
| **State** | `DrillState` — transcript, current question, objection, ruling, done |
| **Nodes** | Functions that read state and return a **partial update** |
| **Edges** | Control flow — Step 2 is only linear; branching comes later |

Objections are a **gate**, not free chat — that is why this is a graph, not
one multi-role prompt. See `../ARCHITECTURE.md` §1.

### Verify Step 2

```bash
cd backend
uv run python -m graph
```

You should see a stub witness message that echoes the sample question.

See `../ROADMAP.md` Phase 0 for sequencing (more persona stubs next,
retrieval and AgentCore in Phase 1).
