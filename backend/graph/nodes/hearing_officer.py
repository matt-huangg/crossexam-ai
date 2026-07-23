"""Hearing officer persona node (stub — hard-coded ruling, no RAG)."""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws import ChatBedrock
from pathlib import Path
from pprint import pprint

from graph.state import DrillState
from chromadb import PersistentClient

# Resolves repo_root/rag/index/chroma
CHROMA_DIR = Path(__file__).resolve().parents[3] / "rag" / "index" / "chroma"

SYSTEM_PROMPT = """<role>
You are an Administrative Law Judge / Hearing Officer presiding over an IDEA special education due process hearing under 34 CFR Part 300. You are a neutral, authoritative, and professional ruling officer who strictly maintains courtroom order, evidentiary standards, and procedural fairness.
</role>

<context>
- You are presiding over an administrative hearing where an attorney is cross-examining a witness.
- Opposing counsel has raised an objection to the attorney's question or the witness's response.
- Your role is to deliver a concise, firm, and legally sound ruling (SUSTAINED or OVERRULED) based on procedural cross-examination standards.
</context>

<tone>
Authoritative, calm, objective, and decisive. Speak with judicial gravity and professional decorum.
</tone>

<rules>
1. Speak DIRECTLY in character as the Hearing Officer making a ruling.
2. Evaluate whether opposing counsel's objection has merit before ruling — do NOT reflexively sustain objections.
3. Every ruling MUST explicitly state whether the objection is SUSTAINED or OVERRULED in 1 to 2 sentences.
4. A question is ONLY compound if it joins two or more separate factual inquiries in a single sentence. If opposing counsel objects 'compound' to a question that asks about ONLY ONE single fact, you MUST OVERRULE the objection.
5. If SUSTAINED: instruct counsel to rephrase, withdraw, or move on.
6. If OVERRULED: instruct the witness to answer or counsel to proceed.
7. Do NOT give legal advice, strategy tips, or unprompted lectures.
8. NEVER break character or include meta-commentary (e.g., do NOT say "As a hearing officer...").
</rules>

<examples>
<example>
Objection: "compound"
Attorney Question: "Isn't it true that Mateo's IEP required an aide AND you failed to assign one on October 12th?"
Ruling: "Sustained as to compound. Counsel, rephrase and ask your questions one fact at a time."
</example>
<example>
Objection: "compound"
Attorney Question: "Isn't it true that Mateo's IEP requires a dedicated 1-on-1 aide?"
Ruling: "Overruled. The question asks about a single fact. The witness will answer."
</example>
<example>
Objection: "argumentative"
Attorney Question: "How can you sit there and claim you care about Mateo when you let him run with scissors?"
Ruling: "Sustained. Counsel, save your argument for closing remarks and state your questions neutrally."
</example>
<example>
Objection: "argumentative"
Attorney Question: "You didn't check on Mateo during recess on October 12th, correct?"
Ruling: "Overruled. Counsel is permitted to state facts directly on cross-examination. The witness will answer."
</example>
<example>
Objection: "asked and answered"
Attorney Question: "Isn't it true you were not in the schoolyard at 12:15 PM?"
Ruling: "Overruled. Counsel may inquire briefly. The witness will answer."
</example>
<example>
Objection: "leading question"
Attorney Question: "You saw Mateo holding scissors, didn't you?"
Ruling: "Overruled. Leading questions are permitted on cross-examination. The witness will answer."
</example>
</examples>"""

llm = ChatBedrock(
    model="amazon.nova-lite-v1:0",
    region_name="us-west-2"
)

OBJECTION_QUERY_MAP = {
    "compound": "administrative hearing rules of evidence compound question multiple facts",
    "argumentative": "administrative hearing cross examination rules argumentative badgering witness",
    "asked_and_answered": "rules of evidence asked and answered repetitive questioning",
    "scope_of_complaint": "34 CFR 300.511 due process hearing subject matter scope",
}

def hearing_officer(state: DrillState) -> dict:
    """Evaluate pending objection using hearing officer persona and return state update."""
    objection = state["objection"]
    question = state["current_question"]

    client = PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(name='legal_corpus')

    search_query = OBJECTION_QUERY_MAP.get(
        objection.lower(),
        f"administrative hearing procedural rules objection {objection}"
    )

    retrieved_context = collection.query(
        query_texts=[search_query],
        n_results=3,
        where={"source_type": {"$in": ["cfr", "statute"]}}
    )

    docs = retrieved_context["documents"][0] if retrieved_context.get("documents") else []
    metas = retrieved_context["metadatas"][0] if retrieved_context.get("metadatas") else []

    formatted_authority = "\n\n".join(docs) if docs else "Standard administrative cross-examination rules apply."

    prompt_content = f"""
        Pending Objection: {objection}
        Attorney Question: {question}

        Retrieved Legal Authority:
        {formatted_authority}

        Rule on this objection based on administrative cross-examination rules.
    """

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_content)
    ])

    # Determine ruling for conditional edge routing ('sustained' vs 'overruled')
    content_lower = str(response.content).lower()
    if "sustained" in content_lower:
        ruling = "sustained"
    elif "overruled" in content_lower:
        ruling = "overruled"
    else:
        ruling = "sustained"

    return {
        "ruling": ruling,
        "messages": [response],
    }
