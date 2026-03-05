"""Configuration settings for PHI Note Generator."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass
class AWSConfig:
    """AWS Bedrock configuration."""
    region: str = "us-east-1"
    model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: int = 5000
    temperature: float = 0.7
    # Retry/timeout settings
    read_timeout: int = 120
    connect_timeout: int = 10
    max_retries: int = 4
    retry_mode: str = "adaptive"


@dataclass
class GeneratorConfig:
    """Note generator configuration."""
    output_dir: Path = field(default_factory=lambda: Path("output"))
    s3_output_path: str | None = None
    notes_subdir: str = "notes"
    manifests_subdir: str = "manifests"
    templates_subdir: str = "templates"

    # Bulk generation settings
    default_batch_size: int = 10

    # Clinical context limits (None = unlimited)
    max_conditions: Optional[int] = 5
    max_medications: Optional[int] = 5
    max_procedures: Optional[int] = 5
    max_allergies: Optional[int] = 5
    max_immunizations: Optional[int] = 5
    max_observations: Optional[int] = 10
    max_imaging_studies: Optional[int] = 5
    max_devices: Optional[int] = 5

    # Encounter selection (-1 = most recent, 0 = oldest, positive = specific index)
    encounter_index: int = -1

    def __post_init__(self):
        """Validate configuration values."""
        # Validate encounter_index
        if self.encounter_index < -1:
            raise ValueError(f"encounter_index must be -1 or >= 0, got {self.encounter_index}")

        # Validate clinical limits
        clinical_limits = [
            ('max_conditions', self.max_conditions),
            ('max_medications', self.max_medications),
            ('max_procedures', self.max_procedures),
            ('max_allergies', self.max_allergies),
            ('max_immunizations', self.max_immunizations),
            ('max_observations', self.max_observations),
            ('max_imaging_studies', self.max_imaging_studies),
            ('max_devices', self.max_devices),
        ]

        for field_name, value in clinical_limits:
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be None or non-negative, got {value}")

    @property
    def notes_dir(self) -> Path:
        return self.output_dir / self.notes_subdir

    @property
    def manifests_dir(self) -> Path:
        return self.output_dir / self.manifests_subdir

    @property
    def template_notes_dir(self) -> Path:
        return self.output_dir / self.templates_subdir / self.notes_subdir

    @property
    def template_manifests_dir(self) -> Path:
        return self.output_dir / self.templates_subdir / self.manifests_subdir

    def ensure_dirs(self, template_mode: bool = False):
        """Create output directories if they don't exist."""
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        if template_mode:
            self.template_notes_dir.mkdir(parents=True, exist_ok=True)
            self.template_manifests_dir.mkdir(parents=True, exist_ok=True)


# Default configurations
DEFAULT_AWS_CONFIG = AWSConfig()
DEFAULT_GENERATOR_CONFIG = GeneratorConfig()
