import sys
from pathlib import Path
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.graph.state import AgentState
from src.agents.emergency_escalation import emergency_escalation_node
from src.agents.router_orchestrator import router_orchestrator_node
from src.agents.policy_inquiry import policy_inquiry_node
from src.agents.claim_action import claim_action_node
from src.agents.claim_validation import claim_validation_node
from src.graph.edges import (
    route_after_emergency_escalation,
    route_from_router_orchestration,
    route_after_policy_inquiry,
    route_after_claim_action,
)


# 1. Initialize State Graph Structure
workflow = StateGraph(AgentState)

# 2. Map Functional Processing Node Implementations
workflow.add_node("emergency_escalation", emergency_escalation_node)
workflow.add_node("router_orchestration", router_orchestrator_node)
workflow.add_node("policy_inquiry", policy_inquiry_node)
workflow.add_node("claim_action", claim_action_node)
workflow.add_node("claim_validation", claim_validation_node)

# 3. Establish Core Infrastructure Paths
workflow.add_edge(START, "emergency_escalation")

workflow.add_conditional_edges(
    "emergency_escalation",
    route_after_emergency_escalation,
    {
        "router_orchestration": "router_orchestration",
        "end": END,
    },
)

workflow.add_conditional_edges(
    "router_orchestration",
    route_from_router_orchestration,
    {
        "policy_inquiry": "policy_inquiry",
        "claim_action": "claim_action",
        "end": END,
    },
)

workflow.add_conditional_edges(
    "policy_inquiry",
    route_after_policy_inquiry,
    {
        "claim_validation": "claim_validation",
        "end": END,
    },
)

workflow.add_conditional_edges(
    "claim_action",
    route_after_claim_action,
    {
        "policy_inquiry": "policy_inquiry",
        "end": END,
    },
)

workflow.add_edge("claim_validation", END)

# 4. Compile State Machine Instance with Local Memory Buffer
memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory)


# --- Local Interactive Integration Test Interface ---
if __name__ == "__main__":
    import uuid

    session_thread = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_thread}}

    print("\n============================================================")
    print("Refactored LangGraph Structural Test Environment")
    print(f"Session Token Tracked (Thread ID: {session_thread})")
    print("Type message and hit Enter. Input 'exit' or 'quit' to terminate.")
    print("============================================================\n")

    while True:
        try:
            user_prompt = input("You: ")
            if user_prompt.strip().lower() in ["exit", "quit"]:
                print("\nSession gracefully shut down. Goodbye!")
                break

            if not user_prompt.strip():
                continue

            output = app_graph.invoke(
                {
                    "messages": [HumanMessage(content=user_prompt)],
                    "user_input": user_prompt,
                },
                config=config,
            )
            print(f"Agent: {output.get('final_response', '[No structural response generated]')}\n")
            
        except KeyboardInterrupt:
            print("\nSession interrupted. Goodbye!")
            break
        except Exception as exc:
            print(f"Error executing refactored workflow topology: {exc}\n")