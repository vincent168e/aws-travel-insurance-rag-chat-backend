from typing import Any, Literal
from pydantic import BaseModel, Field

ServiceCategory = Literal["inquiry", "claim"]
ClaimCategory = Literal[
    "emergency_medical_care",
    "trip_cancellation_or_interruption",
    "baggage",
    "accidental_death_or_dismemberment",
]

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    service_category: ServiceCategory | None = None
    claim_category: ClaimCategory | None = None
    claim_description: str | None = None
    claim_stage: str | None = None
    image_urls: list[str] = Field(default_factory=list)

class ChatResponse(BaseModel):
    thread_id: str
    response: str
    service_category: ServiceCategory | None = None
    claim_category: ClaimCategory | None = None
    claim_description: str | None = None
    session_closed: bool = False
    claim_stage: str | None = None
    audit_report: dict[str, Any] | None = None