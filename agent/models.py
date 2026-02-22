"""Data models for the PII detection agent."""

from __future__ import annotations

from dataclasses import field
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

SUMMARY_MAX_LENGTH = 100
REVIEW_REASON_MAX_LENGTH = 50

class PIIEntity(BaseModel):
    """Represents a single detected PII string to redact."""

    type: str = Field(..., description="Normalized PII type label, e.g. 'email'.")
    value: str = Field(..., description="Exact string text that should be redacted from the document.")

class AgentResponse(BaseModel):
    """
    Structured response returned by the PII agent.

    Args:
        pii_entities: ordered list of PII strings to redact
    """

    pii_entities: list[PIIEntity] = Field(default_factory=list)

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
