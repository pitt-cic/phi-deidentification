"""Data models for the PII detection agent."""

from __future__ import annotations

from dataclasses import field
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from pydantic.dataclasses import dataclass

# HIPAA 18 Identifiers for Protected Health Information (PHI)
DEFAULT_PII_TYPES = [
    "person_name",                          # 1. Name
    "postal_address",                       # 2. Address (all geographic subdivisions smaller than state)
    "date",           # 3. All elements (except years) of dates related to an individual
    "phone_number",                         # 4. Telephone numbers
    "fax_number",                           # 5. Fax number
    "email",                                # 6. Email address
    "ssn",                                  # 7. Social Security Number
    "medical_record_number",                # 8. Medical record number
    "health_plan_beneficiary_number",      # 9. Health plan beneficiary number
    "account_number",                       # 10. Account number
    "certificate_or_license_number",        # 11. Certificate or license number
    "vehicle_identifier",                   # 12. Vehicle identifiers and serial numbers, including license plate numbers
    "device_identifier",                    # 13. Device identifiers and serial numbers
    "url",                                  # 14. Web URL
    "ip_address",                           # 15. Internet Protocol (IP) Address
    "biometric_identifier",                  # 16. Finger or voice print
    "photographic_image",                   # 17. Photographic image
    "other_unique_identifier",             # 18. Any other characteristic that could uniquely identify the individual
]


class PIIEntity(BaseModel):
    """Represents a single detected PII string to redact."""

    type: str = Field(..., description="Normalized PII type label, e.g. 'email'.")
    value: str = Field(..., description="Exact string text that should be redacted from the document.")
    reason: str = Field(..., description="Explanation of why this string is considered PII.")
    confidence: Literal["low", "medium", "high"] = Field(
        ..., 
        description="Confidence level: 'low' (needs human review), 'medium' (may benefit from review), 'high' (no review needed)."
    )


class AgentResponse(BaseModel):
    """
    Structured response returned by the PII agent.

    Args:
        pii_entities: ordered list of PII strings to redact
        summary: concise description of the detected sensitive content
        needs_review: flag to escalate ambiguous cases for human validation
        review_reason: rationale for the review request when needs_review is true
    """

    pii_entities: list[PIIEntity] = Field(default_factory=list)
    summary: str | None = None
    needs_review: bool = False
    review_reason: str | None = None

    @model_validator(mode="after")
    def _ensure_review_reason(cls, values: "AgentResponse") -> "AgentResponse":
        if values.needs_review and not values.review_reason:
            raise ValueError("review_reason must be provided when needs_review is true")
        if not values.needs_review:
            values.review_reason = None
        return values


@dataclass
class DetectionParameters:
    """Fine-grained controls for how the agent extracts PII spans."""

    pii_types: list[str] = field(default_factory=lambda: DEFAULT_PII_TYPES.copy())
    max_entities: int | None = 200

    def __post_init__(self) -> None:
        self.pii_types = self._normalize_types(self.pii_types)
        if self.max_entities is not None and self.max_entities < 1:
            raise ValueError("max_entities must be >= 1")

    @staticmethod
    def _normalize_types(values: list[str] | None) -> list[str]:
        cleaned = [value.strip().lower() for value in values or [] if value.strip()]
        return cleaned or DEFAULT_PII_TYPES.copy()


@dataclass
class AgentContext:
    """
    Context supplied when invoking the agent.

    Args:
        document_text: raw text contents to scan
        source_name: friendly identifier for logs
        language: BCP-47 language tag (defaults to English)
        detection: optional detection parameters
    """

    document_text: str
    source_name: str | None = None
    language: str = "en"
    detection: DetectionParameters = field(default_factory=DetectionParameters)

    def __post_init__(self) -> None:
        if not self.document_text:
            raise ValueError("document_text must not be empty")
        if not self.language:
            self.language = "en"

