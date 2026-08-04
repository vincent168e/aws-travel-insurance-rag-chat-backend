import json
import logging
import re
from typing import Any
from src.graph.state import AgentState

logger = logging.getLogger(__name__)

def log_event(event: str, **details: Any) -> None:
    """Emit compact structured logs for workflow routing and agent activity."""
    parts: list[str] = [event]
    for key, value in details.items():
        if isinstance(value, str) and len(value) > 220:
            value = f"{value[:217]}..."
        parts.append(f"{key}={value!r}")
    logger.info(" | ".join(parts))


def log_node_start(node_name: str, state: AgentState) -> None:
    """Standardized entry logging hook for graph nodes."""
    thread_id = None
    if state.get("messages"):
        try:
            thread_id = state["messages"][0].additional_kwargs.get("thread_id")
        except (AttributeError, IndexError):
            pass

    log_event(
        f"{node_name}.start",
        thread_id=thread_id,
        service_category=state.get("service_category"),
        claim_stage=state.get("claim_stage"),
        clarification_attempts=state.get("clarification_attempts", 0),
        final_response_present=bool(state.get("final_response")),
        user_input=state.get("user_input", ""),
    )


def log_node_end(node_name: str, result: dict[str, Any]) -> None:
    """Standardized exit logging hook for graph nodes."""
    log_event(
        f"{node_name}.end",
        next_agent=result.get("next_agent"),
        service_category=result.get("service_category"),
        claim_stage=result.get("claim_stage"),
        session_closed=bool(result.get("session_closed", False)),
        final_response=result.get("final_response", ""),
    )


def extract_text_content(content: Any) -> str:
    """Safely extracts a plain string from SDK-dependent response payload formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        extracted: list[str] = []
        for block in content:
            if isinstance(block, str):
                extracted.append(block)
            elif isinstance(block, dict) and "text" in block:
                extracted.append(str(block["text"]))
        return "".join(extracted)
    return str(content)


def normalize_user_text(message_like: Any) -> str:
    """Normalizes multi-format incoming message content payloads into simple strings."""
    if isinstance(message_like, str):
        return message_like
    return extract_text_content(message_like)


def parse_json_object(text: str) -> dict[str, Any]:
    """Attempts standard json parsing, falling back to substring regex matching if needed."""
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}
        return {}