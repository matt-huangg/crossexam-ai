from typing import TypedDict, Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class DrillState(TypedDict):
    current_question: str
    messages: Annotated[list[BaseMessage], add_messages]
    objection: str
    ruling: Literal["","sustained", "overruled"]
    done: bool
 