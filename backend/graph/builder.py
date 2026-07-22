"""Compile the cross-examination drill graph (stub nodes, conditional routing).

Session termination always flows ``attorney (done) → debrief → END``. Mid-drill
turn completion returns to ``attorney`` and pauses on ``interrupt`` until the
attorney supplies the next input.
"""

from langgraph.graph import END, START, StateGraph

from graph.nodes.attourney import attourney
from graph.nodes.debrief import debrief
from graph.nodes.hearing_officer import hearing_officer
from graph.nodes.opposing_counsel import opposing_counsel
from graph.nodes.witness import witness
from graph.state import DrillState

NODE_ATTOURNEY = "attourney"
NODE_OPPOSING_COUNSEL = "opposing_counsel"
NODE_DEBRIEF = "debrief"
NODE_HEARING_OFFICER = "hearing_officer"
NODE_WITNESS = "witness"


def route_after_attourney(state: DrillState) -> str:
    """Attorney ends cross → debrief; otherwise continue with opposing counsel."""
    if state["done"]:
        return NODE_DEBRIEF
    return NODE_OPPOSING_COUNSEL


def route_after_objection(state: DrillState) -> str:
    """No objection → witness answers; otherwise hearing officer rules."""
    if state["objection"] == "":
        return NODE_WITNESS
    return NODE_HEARING_OFFICER


def route_after_ruling(state: DrillState) -> str:
    """Sustained → attorney rephrase; overruled → witness answers."""
    if state["ruling"] == "sustained":
        return NODE_ATTOURNEY
    return NODE_WITNESS


def build_graph():
    builder = StateGraph(DrillState)

    builder.add_node(NODE_ATTOURNEY, attourney)
    builder.add_node(NODE_OPPOSING_COUNSEL, opposing_counsel)
    builder.add_node(NODE_HEARING_OFFICER, hearing_officer)
    builder.add_node(NODE_WITNESS, witness)
    builder.add_node(NODE_DEBRIEF, debrief)

    builder.add_edge(START, NODE_ATTOURNEY)
    builder.add_conditional_edges(
        NODE_ATTOURNEY,
        route_after_attourney,
        {NODE_DEBRIEF: NODE_DEBRIEF, NODE_OPPOSING_COUNSEL: NODE_OPPOSING_COUNSEL},
    )
    builder.add_conditional_edges(
        NODE_OPPOSING_COUNSEL,
        route_after_objection,
        {NODE_WITNESS: NODE_WITNESS, NODE_HEARING_OFFICER: NODE_HEARING_OFFICER},
    )
    builder.add_conditional_edges(
        NODE_HEARING_OFFICER,
        route_after_ruling,
        {NODE_ATTOURNEY: NODE_ATTOURNEY, NODE_WITNESS: NODE_WITNESS},
    )
    builder.add_edge(NODE_WITNESS, NODE_ATTOURNEY)
    # Debrief is the only node that may transition to END (end of cross-exam).
    builder.add_edge(NODE_DEBRIEF, END)

    return builder.compile()
