import logging
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.graph.state import AgentState
from src.config import settings
from src.messages import MESSAGES
from src.database.pinecone_client import query_policy_chunks
from src.utils.helpers import log_node_start, log_node_end, log_event, normalize_user_text, extract_text_content


logger = logging.getLogger(__name__)

HARD_CODED_POLICY_TIER = "Single-trip solutions Canada package"

policy_llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0,
)

def policy_inquiry_node(state: AgentState) -> dict:
    log_node_start("policy", state)
    query = state.get("user_input") or normalize_user_text(state["messages"][-1].content)

    if query.strip().lower() == "inquiry service":
        prompt_message = MESSAGES["INQUIRY_START"]
        result = {
            "final_response": prompt_message,
            "next_agent": "end",
            "messages": [AIMessage(content=prompt_message)],
        }
        log_event("policy.initial_inquiry_prompt")
        log_node_end("policy", result)
        return result

    policy_tier = state.get("policy_tier") or HARD_CODED_POLICY_TIER
    log_event("policy.retrieval_start", policy_tier=policy_tier, query=query)

    chunks = query_policy_chunks(query=query, top_k=5, policy_tier=policy_tier)
    max_score = chunks[0]["score"] if chunks else 0.0
    log_event("policy.retrieval_complete", matches=len(chunks), max_score=max_score)

    if not chunks or max_score < 0.35:
        result = {
            "final_response": MESSAGES["NO_REFERENCE_FALLBACK"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["NO_REFERENCE_FALLBACK"])],
        }
        log_event("policy.no_reference_fallback")
        log_node_end("policy", result)
        return result

    context = "\n\n".join(chunk.get("text", "") for chunk in chunks if chunk.get("text"))
    log_event("policy.context_prepared")

    if state.get("service_category") == "claim" or state.get("claim_stage") == "ready_for_audit":
        result = {
            "policy_context": context,
            "next_agent": "claim_validation",
            "final_response": "",
        }
        log_event("policy.route_claim_validation")
        log_node_end("policy", result)
        return result

    system_prompt = (
        "You are a customer service assistant for travel insurance policy inquiries. Be concise and empathatic. "
        "Answer only from the provided context. Keep answer to 2-3 sentences. "
        "if context is not related to travel insurance policy, reply exactly with: "
        f"{MESSAGES['OUT_OF_SCOPE_FALLBACK']}\n\n"
        "If context is insufficient, reply exactly with: "
        f"{MESSAGES['NO_REFERENCE_FALLBACK']}\n\n"
        f"Context:\n{context}\n\n"
        f"User Question: {query}"
    )
    raw = policy_llm.invoke([HumanMessage(content=system_prompt)])
    answer = extract_text_content(raw.content).strip()
    log_event("policy.answer_generated", answer=answer)

    result = {
        "final_response": answer,
        "next_agent": "end",
        "messages": [AIMessage(content=answer)],
    }
    
    if state.get("pending_claim_transition"):
        scenarios = state.get("pending_claim_scenarios") or []
        breakdown_text = "\n\nI can help you file a claim if you need it.\n"
        answer = f"{answer}{breakdown_text}"
        
        result = {
            "final_response": answer,
            "next_agent": "end",
            "claim_stage": "awaiting_claim_category",
            "service_category": "inquiry",
            "user_input": scenarios[0] if scenarios else "", 
            "pending_claim_transition": False,
            "messages": [AIMessage(content=answer)],
        }
    
    log_node_end("policy", result)
    return result