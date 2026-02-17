"""Configuration settings for PHI Note Generator."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List


class PHIType(str, Enum):
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


class NoteType(str, Enum):
    """Supported clinical note types."""
    EMERGENCY_DEPT = "emergency_dept"
    DISCHARGE_SUMMARY = "discharge_summary"
    PROGRESS_NOTE = "progress_note"
    RADIOLOGY_REPORT = "radiology_report"
    TELEHEALTH_CONSULT = "telehealth_consult"


# PHI types typically found in each note type
NOTE_PHI_MAPPING: Dict[NoteType, List[PHIType]] = {
    NoteType.EMERGENCY_DEPT: [
        PHIType.NAME, PHIType.ADDRESS, PHIType.DATE, PHIType.PHONE,
        PHIType.SSN, PHIType.MRN, PHIType.HEALTH_PLAN_ID, PHIType.LICENSE,
        PHIType.VEHICLE_ID, PHIType.EMAIL
    ],
    NoteType.DISCHARGE_SUMMARY: [
        PHIType.NAME, PHIType.ADDRESS, PHIType.DATE, PHIType.PHONE,
        PHIType.MRN, PHIType.HEALTH_PLAN_ID, PHIType.FAX, PHIType.EMAIL
    ],
    NoteType.PROGRESS_NOTE: [
        PHIType.NAME, PHIType.DATE, PHIType.MRN, PHIType.PHONE
    ],
    NoteType.RADIOLOGY_REPORT: [
        PHIType.NAME, PHIType.DATE, PHIType.MRN, PHIType.DEVICE_ID,
        PHIType.ACCOUNT_NUMBER
    ],
    NoteType.TELEHEALTH_CONSULT: [
        PHIType.NAME, PHIType.DATE, PHIType.PHONE, PHIType.EMAIL,
        PHIType.MRN, PHIType.IP_ADDRESS, PHIType.URL
    ],
}


@dataclass
class AWSConfig:
    """AWS Bedrock configuration."""
    region: str = "us-east-1"
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    max_tokens: int = 4000
    temperature: float = 0.7


@dataclass
class GeneratorConfig:
    """Note generator configuration."""
    output_dir: Path = field(default_factory=lambda: Path("output"))
    notes_subdir: str = "notes"
    manifests_subdir: str = "manifests"

    # LLM retry settings
    max_retries: int = 4
    retry_delay_base: int = 5

    # Bulk generation settings
    default_batch_size: int = 10

    @property
    def notes_dir(self) -> Path:
        return self.output_dir / self.notes_subdir

    @property
    def manifests_dir(self) -> Path:
        return self.output_dir / self.manifests_subdir

    def ensure_dirs(self):
        """Create output directories if they don't exist."""
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)


# Default configurations
DEFAULT_AWS_CONFIG = AWSConfig()
DEFAULT_GENERATOR_CONFIG = GeneratorConfig()
