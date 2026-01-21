"""Data models for the PII detection agent."""

from __future__ import annotations

from dataclasses import field
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from pydantic.dataclasses import dataclass

# HIPAA 18 Identifiers for Protected Health Information (PHI)
DEFAULT_PII_TYPES = [
    "person_name",                          
    "address",        
    "date", 
    "phone_number",                         
    "fax_number",                           
    "email",                                
    "ssn",                                  
    "medical_record_number",                
    "health_plan_beneficiary_number",      
    "account_number",                       
    "certificate_or_license_number",        
    "vehicle_identifier",                   
    "device_identifier",                    
    "url",                                  
    "ip_address",                           
    "biometric_identifier",                  
    "photographic_image",                   
    "other",             
]

class PIIEntity(BaseModel):
    """Represents a single detected PII string to redact."""

    type: str = Field(..., description="Normalized PII type label, e.g. 'email'.")
    value: str = Field(..., description="Exact string text that should be redacted from the document.")
    reason: str = Field(..., max_length=50, description="Explanation of why this string is considered PII.")
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
    summary: str | None = Field(default=None, max_length=100)
    needs_review: bool = False
    review_reason: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _ensure_review_reason(self) -> "AgentResponse":
        if self.needs_review and not self.review_reason:
            raise ValueError("review_reason must be provided when needs_review is true")
        if not self.needs_review:
            self.review_reason = None
        return self

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

