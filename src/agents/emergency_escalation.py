import time
import logging
from langchain_core.messages import AIMessage

from src.graph.state import AgentState
from src.config import settings
from src.messages import MESSAGES
from src.constants import EMERGENCY_KEYWORDS
from src.utils.helpers import log_node_start, log_node_end, log_event, normalize_user_text


logger = logging.getLogger(__name__)


def detect_emergency(user_input: str) -> bool:
    """Returns True when emergency intent should trigger live-agent escalation."""
    text_lower = user_input.lower()
    return any(keyword in text_lower for keyword in EMERGENCY_KEYWORDS)


def escalation_webhook_stub(state: AgentState) -> None:
    """Phase-1 placeholder for helpdesk webhook integration."""
    logger.warning(
        "Emergency escalation webhook stub triggered (thread locked). Reason: %s",
        state.get("escalation_reason", "unspecified"),
    )


def emergency_escalation_node(state: AgentState) -> dict:
    log_node_start("emergency_escalation", state)

    current_time = time.time()
    last_activity = state.get("last_activity_timestamp")
    timeout_seconds = 30 * 60

    if last_activity and (current_time - last_activity > timeout_seconds):
        result = {
            "session_closed": True,
            "final_response": MESSAGES["SESSION_TIMEOUT"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["SESSION_TIMEOUT"])],
        }
        log_node_end("emergency_escalation", result)
        return result

    if state.get("session_closed"):
        result = {
            "final_response": MESSAGES["SESSION_CLOSED"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["SESSION_CLOSED"])],
        }
        log_node_end("emergency_escalation", result)
        return result

    user_input = normalize_user_text(state["messages"][-1].content)
    log_event("emergency_escalation.scan", user_input=user_input)

    if detect_emergency(user_input) and state.get("service_category") == "claim":
        escalation_reason = "Emergency keyword override"
        updated_state = {
            "session_closed": True,
            "escalation_reason": escalation_reason,
            "final_response": MESSAGES["EMERGENCY_ESCALATION"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["EMERGENCY_ESCALATION"])],
            "last_activity_timestamp": current_time,
        }
        escalation_webhook_stub({**state, **updated_state})
        log_node_end("emergency_escalation", updated_state)
        return updated_state

    result = {
        "next_agent": "router",
        "final_response": "",
        "last_activity_timestamp": current_time,
    }
    
    if state.get("service_category") == "inquiry":
        result["claim_stage"] = None

    log_node_end("emergency_escalation", result)
    return result