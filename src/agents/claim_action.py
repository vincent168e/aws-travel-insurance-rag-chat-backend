import logging
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.graph.state import AgentState
from src.config import settings
from src.messages import MESSAGES
from src.utils.helpers import log_node_start, log_node_end, log_event, normalize_user_text, extract_text_content


logger = logging.getLogger(__name__)

action_llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0,
)

def extract_from_images(image_urls: list[str], claim_category: str, claim_description: str) -> list[str]:
    """Use Gemini multimodal endpoint to extract claim-relevant evidence text from images."""
    if not image_urls:
        return []

    prompt = (
        "Extract key insurance-claim facts from the provided image(s). "
        "Prioritize: dates, names, flight numbers, amounts, diagnosis/events, and official statements. "
        "Keep output concise and factual.\n"
        f"Claim category: {claim_category}\n"
        f"Claim description: {claim_description}"
    )

    content_blocks: list[dict] = [{"type": "text", "text": prompt}]
    for url in image_urls:
        content_blocks.append({"type": "image_url", "image_url": {"url": url}})

    try:
        raw = action_llm.invoke([HumanMessage(content=content_blocks)])
        text = extract_text_content(raw.content).strip()
        return [text] if text else []
    except Exception as exc:
        logger.warning("OCR extraction failed: %s", exc)
        return []


def claim_action_node(state: AgentState) -> dict:
    log_node_start("claims_action", state)

    claim_category = state.get("claim_category")
    claim_description = (state.get("claim_description") or "").strip()
    image_urls = state.get("image_urls") or []

    latest_user_text = normalize_user_text(state["messages"][-1].content).strip()
    current_stage = state.get("claim_stage")

    if current_stage == "awaiting_claim_category" and not claim_category:
        claim_category = latest_user_text
        log_event("claims_action.slot_filled", slot="claim_category", value=claim_category)
        
    elif current_stage == "awaiting_description" and not claim_description:
        claim_description = latest_user_text
        log_event("claims_action.slot_filled", slot="claim_description", value=claim_description)

    log_event(
        "claims_action.slot_check",
        claim_category=claim_category,
        claim_description_present=bool(claim_description),
        image_count=len(image_urls),
    )

    if not claim_category:
        result = {
            "claim_stage": "awaiting_claim_category",
            "final_response": MESSAGES["CLAIM_CATEGORY"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["CLAIM_CATEGORY"])],
        }
        log_event("claims_action.awaiting_claim_category")
        log_node_end("claims_action", result)
        return result

    if not claim_description:
        result = {
            "claim_stage": "awaiting_description",
            "final_response": MESSAGES["CLAIM_DESCRIPTION"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["CLAIM_DESCRIPTION"])],
            "claim_category": claim_category,
        }
        log_event("claims_action.awaiting_description")
        log_node_end("claims_action", result)
        return result

    if not image_urls:
        result = {
            "claim_stage": "awaiting_images",
            "final_response": MESSAGES["CLAIM_IMAGE_PROOF"],
            "next_agent": "end",
            "messages": [AIMessage(content=MESSAGES["CLAIM_IMAGE_PROOF"])],
            "claim_category": claim_category,
            "claim_description": claim_description,
        }
        log_event("claims_action.awaiting_images")
        log_node_end("claims_action", result)
        return result

    log_event("claims_action.ocr_start", image_count=len(image_urls))
    ocr_extracts = extract_from_images(image_urls, claim_category, claim_description)
    if not ocr_extracts:
        clarification = (
            "I could not extract enough details from your image attachments. "
            "Please upload clearer images or add key details in text."
        )
        result = {
            "claim_stage": "awaiting_images",
            "final_response": clarification,
            "next_agent": "end",
            "messages": [AIMessage(content=clarification)],
            "claim_category": claim_category,
            "claim_description": claim_description,
        }
        log_event("claims_action.ocr_insufficient")
        log_node_end("claims_action", result)
        return result

    retrieval_query = (
        f"Claim category: {claim_category}. Description: {claim_description}. "
        f"Evidence: {' '.join(ocr_extracts)}"
    )
    log_event("claims_action.ready_for_policy_audit", retrieval_query=retrieval_query)

    result = {
        "ocr_extracts": ocr_extracts,
        "user_input": retrieval_query,
        "claim_stage": "ready_for_audit",
        "next_agent": "policy_inquiry",
        "final_response": "",
        "claim_category": claim_category,
        "claim_description": claim_description,
    }
    log_node_end("claims_action", result)
    return result