"""Debrief node (stub — structured feedback from transcript, no LLM yet).

Produces post-drill feedback on cross-examination technique for the rehearsal
tool. Does not evaluate case merits or recommend legal strategy.
"""

from langchain_core.messages import AIMessage

from graph.state import DrillState


def debrief(state: DrillState) -> dict:
    """Append a structured practice report based on the session transcript."""
    message_count = len(state["messages"])
    last_objection = state["objection"] or "(none on final turn)"
    last_ruling = state["ruling"] or "(none on final turn)"

    feedback = (
        "(Stub debrief — rehearsal feedback only, not legal advice.)\n"
        f"Transcript messages: {message_count}.\n"
        f"Last objection ground: {last_objection}. Last ruling: {last_ruling}.\n"
        "Practice focus: avoid compound questions; after a sustained objection, "
        "rephrase before expecting an answer."
    )
    return {"messages": [AIMessage(content=feedback)]}
