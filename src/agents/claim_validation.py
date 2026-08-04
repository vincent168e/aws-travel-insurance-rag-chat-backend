import logging
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.graph.state import AgentState
from src.config import settings
from src.messages import MESSAGES
from src.utils.helpers import log_node_start, log_node_end, log_event, parse_json_object, extract_text_content


logger = logging.getLogger(__name__)

HARD_CODED_POLICY_TIER = "Single-trip solutions Canada package"
HARD_CODED_PREPAYMENT_OPTION = True

validation_llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0,
)

def claim_validation_node(state: AgentState) -> dict:
    log_node_start("claim_validation", state)
    claim_category = state.get("claim_category", "")
    claim_description = state.get("claim_description", "")
    ocr_extracts = state.get("ocr_extracts") or []
    policy_context = state.get("policy_context", "")
    attempts = int(state.get("clarification_attempts", 0))
    
    log_event(
        "claim_validation.audit_start",
        claim_category=claim_category,
        description_length=len(claim_description.strip()),
        ocr_extract_count=len(ocr_extracts),
        policy_context_present=bool(policy_context.strip()),
        clarification_attempts=attempts,
    )

    unclear_reasons: list[str] = []
    if len(claim_description.strip()) < 20:
        unclear_reasons.append("case description is too short")
    if not ocr_extracts:
        unclear_reasons.append("no extractable document evidence found")
    if not policy_context.strip():
        unclear_reasons.append("no matching policy clauses were retrieved")

    if unclear_reasons:
        attempts += 1
        log_event("claim_validation.unclear", reasons=unclear_reasons, attempts=attempts)
        if attempts > 2:
            result = {
                "clarification_attempts": 0,
                "claim_stage": "reset",
                "claim_category": "",
                "claim_description": "",
                "image_urls": [],
                "ocr_extracts": [],
                "policy_context": "",
                "audit_report": {
                    "status": "Flagged_For_Review",
                    "reason": "Exceeded clarification retries",
                },
                "final_response": MESSAGES["CLAIM_RESET"],
                "next_agent": "end",
                "messages": [AIMessage(content=MESSAGES["CLAIM_RESET"])],
            }
            log_event("claim_validation.reset_after_retries")
            log_node_end("claim_validation", result)
            return result

        clarification_message = (
            "I need clarification before validating this claim: "
            + "; ".join(unclear_reasons)
            + ". Please provide the missing details and I will re-audit your case."
        )
        result = {
            "clarification_attempts": attempts,
            "claim_stage": "awaiting_clarification",
            "audit_report": {
                "status": "Flagged_For_Review",
                "reason": "; ".join(unclear_reasons),
                "clarification_attempts": attempts,
            },
            "final_response": clarification_message,
            "next_agent": "end",
            "messages": [AIMessage(content=clarification_message)],
        }
        log_event("claim_validation.request_clarification", message=clarification_message)
        log_node_end("claim_validation", result)
        return result

    validation_prompt = (
        "You are a claim validation auditor. Return JSON only with keys: "
        "status, possible_coverage_amount, rationale, flagged_items. "
        "status must be either Passed or Flagged_For_Review.\n"
        f"Plan name: {HARD_CODED_POLICY_TIER}\n"
        f"Prepayment option: {HARD_CODED_PREPAYMENT_OPTION}\n"
        f"Claim category: {claim_category}\n"
        f"Case description: {claim_description}\n"
        f"Extracted evidence: {' '.join(ocr_extracts)}\n"
        f"Policy snippets: {policy_context[:6000]}\n"
    )

    raw = validation_llm.invoke([HumanMessage(content=validation_prompt)])
    parsed = parse_json_object(extract_text_content(raw.content))
    log_event("claim_validation.model_response", parsed=parsed)

    status = parsed.get("status", "Flagged_For_Review")
    if status not in {"Passed", "Flagged_For_Review"}:
        status = "Flagged_For_Review"

    possible_coverage_amount = parsed.get("possible_coverage_amount", "Not determined")
    rationale = parsed.get("rationale", "Validation completed with limited details.")
    flagged_items = parsed.get("flagged_items", [])
    if not isinstance(flagged_items, list):
        flagged_items = [str(flagged_items)]

    report = {
        "status": status,
        "policy_tier": HARD_CODED_POLICY_TIER,
        "prepayment_option": HARD_CODED_PREPAYMENT_OPTION,
        "possible_coverage_amount": possible_coverage_amount,
        "rationale": rationale,
        "flagged_items": flagged_items,
    }

    response_text = (
        f"Validation result: {status}. Possible coverage amount: {possible_coverage_amount}. "
        f"Reason: {rationale}."
    )
    log_event("claim_validation.completed", status=status, possible_coverage_amount=possible_coverage_amount)

    result = {
        "clarification_attempts": 0,
        "claim_stage": "completed" if status == "Passed" else "awaiting_clarification",
        "audit_report": report,
        "final_response": response_text,
        "next_agent": "end",
        "messages": [AIMessage(content=response_text)],
    }
    log_node_end("claim_validation", result)
    return result