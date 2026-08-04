import logging
from src.graph.state import AgentState
from src.utils.helpers import log_event


logger = logging.getLogger(__name__)


def route_after_emergency_escalation(state: AgentState) -> str:
    """Evaluates whether an emergency fallback or a timeout state was encountered."""
    log_event(
        "route.after_emergency_escalation",
        next_agent=state.get("next_agent"),
        final_response_present=bool(state.get("final_response")),
        session_closed=bool(state.get("session_closed", False)),
    )
    if state.get("next_agent") == "end" or state.get("final_response"):
        return "end"
    return "router_orchestration"


def route_from_router_orchestration(state: AgentState) -> str:
    """Directs the workflow stream based on intent categorization results."""
    next_agent = state.get("next_agent", "end")
    log_event("route.from_router_orchestration", next_agent=next_agent)
    return next_agent


def route_after_policy_inquiry(state: AgentState) -> str:
    """Routes the state machine to validation if an active claims workflow context exists."""
    next_agent = state.get("next_agent", "end")
    log_event("route.after_policy_inquiry", next_agent=next_agent)
    return next_agent


def route_after_claim_action(state: AgentState) -> str:
    """Tracks whether parameter acquisition has completed and shifts logic to validation checking."""
    next_agent = state.get("next_agent", "end")
    log_event("route.after_claim_action", next_agent=next_agent)
    return next_agent