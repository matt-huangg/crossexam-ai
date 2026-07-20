"""Compile the drill LangGraph (Step 2: one stub node).

Tiny graph for learning the compile/invoke loop:

  START → witness → END

Later steps add opposing counsel, hearing officer, conditional edges, and
eventually real LLM + RAG. AgentCore stays out of scope until this runs
locally.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graph.nodes.witness import witness_node
from graph.state import DrillState


def build_graph():
    """Build and compile the Step 2 drill graph (witness stub only)."""
    builder = StateGraph(DrillState)
    # Register the node under a stable name — edges and later routing use this.
    builder.add_node("witness", witness_node)
    builder.add_edge(START, "witness")
    builder.add_edge("witness", END)
    return builder.compile()


def main() -> None:
    """Invoke the stub graph once with a fake attorney question."""
    graph = build_graph()
    # Initial state: only the fields we care about for this turn. ``messages``
    # starts empty; the witness node appends via the add_messages reducer.
    result = graph.invoke(
        {
            "messages": [],
            "current_question": "You never provided the student with speech therapy, correct?",
            "objection": "",
            "ruling": "",
            "done": False,
        }
    )
    print("current_question:", result["current_question"])
    print("messages:")
    for msg in result["messages"]:
        print(f"  [{msg.type}] {msg.content}")


if __name__ == "__main__":
    main()
