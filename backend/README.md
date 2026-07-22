# backend

LangGraph cross-examination drill — rebuild this yourself to learn the
primitives. Deps are already in `pyproject.toml` (`langgraph`, `langchain-core`).

## Setup

```bash
cd backend
uv sync
```

## Rebuild order (type it by hand)

Leave `ARCHITECTURE.md` §1 open while you do this — it is the flowchart you
are encoding.

1. **`graph/state.py`** — `DrillState` (`TypedDict`)
   - Fields that multiple nodes will share: `messages`, `current_question`,
     `objection`, `ruling`, `done`
   - Use `Annotated[..., add_messages]` on `messages` so appends don't wipe
     the transcript

2. **`graph/nodes/witness.py`** — one stub node
   - Signature: `state in → partial update dict out`
   - Hard-coded answer is fine; no LLM yet

3. **`graph/build.py`** — wire the graph
   - `StateGraph(DrillState)` → `add_node` → `add_edge(START, ...)` →
     `compile()` → `invoke({...})`
   - First target: `START → witness → END`

4. **`graph/__main__.py`** — call `build.main` so this works:

```bash
uv run python -m graph
```

5. **Next learning step** — add `opposing_counsel` stub, still linear:

```text
START → opposing_counsel → witness → END
```

Then conditional edges on `objection` / `ruling`.

## Out of scope until the graph feels boring

LLM calls, Chroma retrieval, case files, AgentCore.
