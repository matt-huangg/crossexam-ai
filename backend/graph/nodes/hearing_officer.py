"""Hearing officer persona node (stub — hard-coded ruling, no RAG)."""

from langchain_core.messages import AIMessage

from graph.state import DrillState


def hearing_officer(state: DrillState) -> dict:
    """Return a hard-coded sustained ruling for the pending objection."""
    objection = state["objection"]
    ruling = "overruled"
    return {
        "ruling": ruling,
        "messages": [AIMessage(content=f"Overruled — {objection}.")],
    }
