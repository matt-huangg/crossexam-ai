from langchain_core.messages import AIMessage
from graph.state import DrillState

def opposing_counsel(state: DrillState) -> dict:
    question = state["current_question"]
    content = "Objection - compound"
    return {
        "objection": "compound",
        "messages": [AIMessage(content=content)]
    }