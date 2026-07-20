"""Shared state for the cross-examination drill LangGraph.

LangGraph carries one state object through every node. Nodes read fields they
need and return a partial update; the graph merges those updates into the
next state. Defining that shape first (this file) is Step 1 — before any
nodes, edges, LLM calls, RAG, or AgentCore.

Why these fields exist (tied to ARCHITECTURE.md §1):

  messages          Full turn transcript. Annotated with ``add_messages`` so
                    each node can append without overwriting prior turns.
  current_question  The attorney's latest question. Witness / opposing counsel
                    / hearing officer all need the same string in play while
                    an objection is pending.
  objection         Opposing counsel's ground (e.g. "compound"), or "" if none.
                    Empty string (not None) keeps the TypedDict simple and
                    matches the "no None in metadata" habit from rag/.
  ruling            Hearing officer outcome: "" | "sustained" | "overruled".
                    Conditional edges will branch on this later.
  done              True when the attorney ends questioning → debrief.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Ruling = Literal["", "sustained", "overruled"]


class DrillState(TypedDict):
    """State carried across turns of the cross-examination drill.

    Every persona node will receive this dict and return a partial update.
    Step 2 wires a hard-coded witness stub; other personas come later.
    """

    # Reducer: append new messages instead of replacing the whole list.
    messages: Annotated[list[BaseMessage], add_messages]
    current_question: str
    objection: str
    ruling: Ruling
    done: bool
