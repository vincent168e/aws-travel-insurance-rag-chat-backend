import logging
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.graph.state import AgentState
from src.config import settings
from src.messages import MESSAGES
from src.constants import COMPETITORS
from src.utils.helpers import (
    log_node_start, 
    log_node_end, 
    log_event, 
    normalize_user_text, 
    parse_json_object, 
    extract_text_content
)


logger = logging.getLogger(__name__)

HARD_CODED_POLICY_TIER = "Single-trip solutions Canada package"

classifier_llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0,
)

def check_competitor_guardrail(user_input: str) -> bool:
    """Returns True if a competitor name is explicitly detected."""
    text_lower = user_input.lower()
    return any(competitor in text_lower for competitor in COMPETITORS)


def decompose_complex_query(text: str) -> dict:
    """Uses the fast classifier to safely unpack complex, multi-part inquiries."""
    prompt = (
        "You are an AI routing assistant for a travel insurance platform.\n"
        "Analyze the user's input and determine if they are asking a policy question, "
        "trying to file claims for multiple incidents, or doing both (mixed).\n\n"
        "Decompose the input into a clean policy inquiry and an explicit list of claim scenarios.\n\n"
        "Return ONLY a JSON object with this exact schema:\n"
        "{\n"
        "  \"intent\": \"inquiry\" | \"claim\" | \"mixed\",\n"
        "  \"policy_inquiry\": \"The isolated coverage question text, or null if none\",\n"
        "  \"claim_scenarios\": [\"List of isolated descriptions for each claim incident mentioned\"]\n"
        "}\n\n"
        f"User Input: {text}\n"
    )
    try:
        raw = classifier_llm.invoke([HumanMessage(content=prompt)])
        return parse_json_object(extract_text_content(raw.content))
    except Exception as exc:
        logger.warning("LLM query decomposition failed, falling back to basic routing: %s", exc)
        return {"intent": "inquiry", "policy_inquiry": text, "claim_scenarios": []}


def router_orchestrator_node(state: AgentState) -> dict:
    log_node_start("router", state)
    user_input = normalize_user_text(state["messages"][-1].content)
    
    if check_competitor_guardrail(user_input):
        result = {
            "final_response": MESSAGES["OUT_OF_SCOPE_FALLBACK"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["OUT_OF_SCOPE_FALLBACK"])],
        }
        return result

    analysis = decompose_complex_query(user_input)
    intent = analysis.get("intent", "inquiry")
    scenarios = analysis.get("claim_scenarios", [])

    log_event("router.analysis_complete", intent=intent, found_scenarios=len(scenarios))

    if intent == "mixed" or len(scenarios) > 1:
        result = {
            "user_input": analysis.get("policy_inquiry") or "What is the total coverage of the plan?",
            "pending_claim_transition": True,
            "pending_claim_scenarios": scenarios,
            "next_agent": "policy_inquiry",
            "final_response": "",
        }
        log_node_end("router", result)
        return result

    if intent == "claim" or state.get("service_category") == "claim":
        result = {
            "next_agent": "claim_action",
            "policy_tier": state.get("policy_tier") or HARD_CODED_POLICY_TIER,
            "final_response": "",
        }
        return result

    result = {
        "next_agent": "policy_inquiry",
        "policy_tier": state.get("policy_tier") or HARD_CODED_POLICY_TIER,
        "final_response": "",
    }
    return result