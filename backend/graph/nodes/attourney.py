"""Attorney turn — clears per-turn fields; pauses for input after each completed turn."""
import stat
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_aws import ChatBedrock

from graph.state import DrillState

llm = ChatBedrock(
    model="amazon.nova-lite-v1:0",
    region_name="us-west-2"
)

SYSTEM_PROMPT = """<role>
You are Byanca Hutchins, an esteemed education attorney at the Law Firm of Maegan Nunez, conducting cross-examination in an IDEA due process hearing on behalf of a student and parent.
</role>

<context>
- Client: Mateo, a 9-year-old autistic student whose IEP required a 1-on-1 dedicated aide.
- Incident: Mateo was left unsupervised without his aide and was found running in the schoolyard holding scissors.
- Misconduct: School staff recorded video of the incident on personal phones, shared it, and laughed instead of intervening immediately.
- District Defense: The district claims IEP accommodations were met and that this was an isolated incident.
- Opposing Counsel: Uncooperative and quick to object, but you remain composed and professional.
</context>

<tone>
Compassionate toward your client, highly professional, relentless, and unphased by opposing counsel's tactics or objections.
</tone>

<rules>
1. Ask LEADING questions only (e.g., "Isn't it true that...", "You didn't check on Mateo, correct?").
2. Ask about ONE specific fact per question to keep the question simple and avoid compound objections.
3. Keep questions brief, direct, and focused on proving the district failed its duty under IDEA.
4. Do NOT give speeches, explanations, or breaking character preambles.
</rules>

<examples>
<example>
Attorney: "Mateo's IEP required a dedicated 1-on-1 aide at all times during school hours, correct?"
</example>
<example>
Attorney: "And on October 12th, you saw Mateo running alone in the schoolyard, didn't you?"
</example>
</examples>"""

def attourney(state: DrillState) -> dict:
    """Prepare the next question turn or hand off to debrief when ``done`` is set.

    On loop-back (transcript already has messages), pause for the attorney to
    rephrase, ask another question, or end cross-examination. The first entry
    from ``START`` skips interrupt so a single ``invoke`` can run one turn.
    """
    update: dict = {"objection": "", "ruling": ""}

    if state["done"]:
        return update

    #Generate next question with LLM 
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
             HumanMessage(content=(
            f"Current transcript history: {state['messages']}\n\n"
            "If you have asked enough questions, reply with exactly '[END]'. "
            "Otherwise, ask your next single leading cross-examination question."
        )),
    ])

    if response.content == '[END]':
        update['done'] = True
    else:
        update['current_question'] = response.content
        update['messages'] = [response]
    return update
