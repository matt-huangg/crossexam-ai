"""Witness persona node (Step 2 stub — hard-coded, no LLM).

A LangGraph node is a function: ``state in → partial update out``. This stub
proves that wiring works before we invest in prompts, case-file RAG, or the
"resist leading questions" behavior that matters for the real product.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from graph.state import DrillState


def witness_node(state: DrillState) -> dict:
    """Return a hard-coded witness reply for the current question.

    Reads ``current_question`` so you can see the node using state. Does not
    touch objection / ruling / done — those belong to other personas later.
    """
    question = state["current_question"]
    # Deliberately wooden: we want the graph mechanics visible, not realism.
    answer = (
        f"(stub witness) I'm not sure I agree with that characterization. "
        f"You asked: {question!r}"
    )
    return {
        "messages": [AIMessage(content=answer)],
    }
