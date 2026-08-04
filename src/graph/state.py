from typing import Annotated, Any, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Definitive schema tracking execution state across all LangGraph nodes."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_input: str
    service_category: str
    claim_category: str
    claim_description: str
    image_urls: list[str]
    ocr_extracts: list[str]
    policy_tier: str
    policy_context: str
    pending_claim_transition: bool
    pending_claim_scenarios: list[str]
    claim_stage: str | None
    clarification_attempts: int
    audit_report: dict[str, Any]
    next_agent: str
    final_response: str
    session_closed: bool
    escalation_reason: str
    last_activity_timestamp: float