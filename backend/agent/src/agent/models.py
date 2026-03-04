"""Data models for the PII detection agent."""

from __future__ import annotations

from dataclasses import field
from pydantic import BaseModel, Field
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

# Short codes for compact LLM output (reduces output tokens by ~60-70%)
SHORT_TO_FULL_TYPE: dict[str, str] = {
    "nam": "person_name",
    "adr": "address",
    "dat": "date",
    "phn": "phone_number",
    "fax": "fax_number",
    "eml": "email",
    "ssn": "ssn",
    "mrn": "medical_record_number",
    "hpb": "health_plan_beneficiary_number",
    "acc": "account_number",
    "lic": "certificate_or_license_number",
    "vin": "vehicle_identifier",
    "dev": "device_identifier",
    "url": "url",
    "ip": "ip_address",
    "bio": "biometric_identifier",
    "img": "photographic_image",
    "oth": "other",
}

FULL_TO_SHORT_TYPE: dict[str, str] = {v: k for k, v in SHORT_TO_FULL_TYPE.items()}

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
    compacted: CompactAgentResponse | None = Field(None, description="Optional compacted format with values grouped by type code")


class CompactAgentResponse(BaseModel):
    """Grouped PII values by type code. Used for token-efficient LLM output."""

    nam: list[str] = Field(default_factory=list, description="Names")
    adr: list[str] = Field(default_factory=list, description="Addresses")
    dat: list[str] = Field(default_factory=list, description="Dates")
    phn: list[str] = Field(default_factory=list, description="Phones")
    fax: list[str] = Field(default_factory=list, description="Fax numbers")
    eml: list[str] = Field(default_factory=list, description="Emails")
    ssn: list[str] = Field(default_factory=list, description="SSNs")
    mrn: list[str] = Field(default_factory=list, description="MRNs")
    hpb: list[str] = Field(default_factory=list, description="Health plan IDs")
    acc: list[str] = Field(default_factory=list, description="Account numbers")
    lic: list[str] = Field(default_factory=list, description="Licenses")
    vin: list[str] = Field(default_factory=list, description="Vehicle IDs")
    dev: list[str] = Field(default_factory=list, description="Device IDs")
    url: list[str] = Field(default_factory=list, description="URLs")
    ip: list[str] = Field(default_factory=list, description="IP addresses")
    bio: list[str] = Field(default_factory=list, description="Biometrics")
    img: list[str] = Field(default_factory=list, description="Photos")
    oth: list[str] = Field(default_factory=list, description="Other PHI")


def expand_compact_response(compact: CompactAgentResponse) -> AgentResponse:
    """Convert compact grouped format back to standard PIIEntity list.

    Args:
        compact: Response with values grouped by short type codes

    Returns:
        AgentResponse with flat list of PIIEntity objects
    """
    entities: list[PIIEntity] = []
    for short_code, full_type in SHORT_TO_FULL_TYPE.items():
        values = getattr(compact, short_code, [])
        for value in values:
            entities.append(PIIEntity(type=full_type, value=value))
    return AgentResponse(pii_entities=entities, compacted=compact)


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
