"""Data models for clinical note generation and PHI tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import List


class PHIType(StrEnum):
    """HIPAA 18 PHI Identifier Types."""
    NAME = "NAME"
    ADDRESS = "ADDRESS"
    DATE = "DATE"
    PHONE = "PHONE"
    FAX = "FAX"
    EMAIL = "EMAIL"
    SSN = "SSN"
    MRN = "MRN"
    HEALTH_PLAN_ID = "HEALTH_PLAN_ID"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    LICENSE = "LICENSE"
    VEHICLE_ID = "VEHICLE_ID"
    DEVICE_ID = "DEVICE_ID"
    URL = "URL"
    IP_ADDRESS = "IP_ADDRESS"
    BIOMETRIC = "BIOMETRIC"
    PHOTO = "PHOTO"
    OTHER = "OTHER"

class NoteType(StrEnum):
    """Supported clinical note types."""
    EMERGENCY_DEPT = "emergency_dept"
    DISCHARGE_SUMMARY = "discharge_summary"
    PROGRESS_NOTE = "progress_note"
    RADIOLOGY_REPORT = "radiology_report"
    TELEHEALTH_CONSULT = "telehealth_consult"

@dataclass
class PHIValue:
    """A generated PHI value with its type."""
    phi_type: PHIType
    value: str

    def to_dict(self) -> dict:
        return {
            "type": self.phi_type.value,
            "value": self.value
        }

@dataclass
# class PHIEntity:
class PHIEntity(PHIValue):
    """A PHI entity found in generated text."""
    # phi_type: PHIType
    # value: str
    start: int
    end: int

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            # "type": self.phi_type.value,
            # "value": self.value,
            "start": self.start,
            "end": self.end
        }

@dataclass
class InjectedPHI:
    """PHI values injected to supplement Synthea data."""
    # Contact info not in Synthea
    email: str = ""
    fax: str = ""

    # Identifiers not in Synthea
    health_plan_id: str = ""
    account_number: str = ""
    vehicle_id: str = ""
    license_plate: str = ""

    # Technical identifiers
    ip_address: str = ""
    patient_portal_url: str = ""

    # Emergency contact (often not in FHIR)
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    emergency_contact_relationship: str = ""

    # Provider contact info
    provider_fax: str = ""
    provider_email: str = ""

    # Facility info
    facility_name: str = ""
    facility_phone: str = ""
    facility_fax: str = ""

    # Device IDs (supplement if not in bundle)
    device_id: str = ""
    scanner_id: str = ""

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "fax": self.fax,
            "health_plan_id": self.health_plan_id,
            "account_number": self.account_number,
            "vehicle_id": self.vehicle_id,
            "license_plate": self.license_plate,
            "ip_address": self.ip_address,
            "patient_portal_url": self.patient_portal_url,
            "emergency_contact_name": self.emergency_contact_name,
            "emergency_contact_phone": self.emergency_contact_phone,
            "emergency_contact_relationship": self.emergency_contact_relationship,
            "provider_fax": self.provider_fax,
            "provider_email": self.provider_email,
            "facility_name": self.facility_name,
            "facility_phone": self.facility_phone,
            "facility_fax": self.facility_fax,
            "device_id": self.device_id,
            "scanner_id": self.scanner_id,
        }


@dataclass
class GeneratedNote:
    """A generated clinical note with its manifest."""
    note_id: str
    note_type: NoteType
    content: str
    phi_entities: List[PHIEntity] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    is_template: bool = False
    placeholders: List[str] = field(default_factory=list)

    def to_manifest(self) -> dict:
        phi_entities_set = set()
        phi_entities = []
        for e in self.phi_entities:
            entity_dict = e.to_dict()
            unique_entity = (entity_dict["type"], entity_dict["value"], entity_dict["start"], entity_dict["end"])
            if unique_entity not in phi_entities_set:
                phi_entities_set.add(unique_entity)
                phi_entities.append(entity_dict)

        manifest = {
            "note_id": self.note_id,
            "note_type": self.note_type.value,
            "generated_at": self.generated_at.isoformat(),
            "phi_entities": phi_entities
        }
        if self.is_template:
            manifest["is_template"] = True
            manifest["placeholders"] = self.placeholders
        return manifest
