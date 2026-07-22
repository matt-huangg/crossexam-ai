"""Entry point: ``cd backend && uv run python -m graph``."""

import subprocess
from graph.builder import build_graph

if __name__ == "__main__":
    graph = build_graph()

    initial_state = {
        "messages": [],
        "current_question": "Mrs. Rodriguez, isn't it true the school provided an aide?",
        "objection": "",
        "ruling": "",
        "done": False,
    }

    print("--- STARTING DRILL ---")

    for event in graph.stream(initial_state, stream_mode="updates"):
        for node_name, update in event.items():
            print(f"\n[NODE EXECUTED: {node_name}]")

            # Handle graph interrupt event
            if node_name == "__interrupt__":
                print("  (Graph paused for human input)")
                continue

            # Print messages cleanly if present
            if isinstance(update, dict) and "messages" in update:
                for msg in update["messages"]:
                    print(f"  {node_name.upper()}: \"{msg.content}\"")

            # Print scalar field updates (like objection or ruling)
            if isinstance(update, dict):
                for key, val in update.items():
                    if key != "messages" and val:
                        print(f"  {key}: {val}")

    mermaid = graph.get_graph().draw_mermaid()
    try:
        subprocess.run(["pbcopy"], input=mermaid.encode(), check=True)
        print("\nMermaid copied to clipboard")
    except Exception:
        pass
