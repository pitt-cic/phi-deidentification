"""Clinical note generator using LLM with PHI injection."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .bedrock_client import BedrockClient
from .config import (
    DEFAULT_GENERATOR_CONFIG,
    GeneratorConfig,
    NoteType,
    NOTE_PHI_MAPPING,
    PHIType,
)
from .phi_generator import PHIGenerator


@dataclass
class PHIEntity:
    """A PHI entity found in generated text."""
    phi_type: PHIType
    value: str
    start: int
    end: int

    def to_dict(self) -> dict:
        return {
            "type": self.phi_type.value,
            "value": self.value,
            "start": self.start,
            "end": self.end
        }


@dataclass
class GeneratedNote:
    """A generated clinical note with its manifest."""
    note_id: str
    note_type: NoteType
    content: str
    phi_entities: List[PHIEntity] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_manifest(self) -> dict:
        return {
            "note_id": self.note_id,
            "note_type": self.note_type.value,
            "generated_at": self.generated_at.isoformat(),
            "phi_entities": [e.to_dict() for e in self.phi_entities]
        }


class NoteGenerator:
    """Generate clinical notes with embedded PHI using LLM."""

    def __init__(
        self,
        bedrock_client: Optional[BedrockClient] = None,
        phi_generator: Optional[PHIGenerator] = None,
        config: Optional[GeneratorConfig] = None
    ):
        self.bedrock = bedrock_client or BedrockClient()
        self.phi_gen = phi_generator or PHIGenerator()
        self.config = config or DEFAULT_GENERATOR_CONFIG
        self.prompts_dir = Path(__file__).parent / "prompts"

    def _load_prompt_template(self, note_type: NoteType) -> str:
        """Load a prompt template for the given note type."""
        template_path = self.prompts_dir / f"{note_type.value}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")
        return template_path.read_text()

    def _build_phi_context_string(self, patient_context: dict) -> str:
        """Build a string representation of PHI for the prompt."""
        lines = [
            f"Patient Name: {patient_context['full_name']}",
            f"Date of Birth: {patient_context['dob']}",
            f"Age: {patient_context['age']} years old",
            f"Gender: {patient_context['gender']}",
            f"SSN: {patient_context['ssn']}",
            f"MRN: {patient_context['mrn']}",
            f"Phone: {patient_context['phone']}",
            f"Email: {patient_context['email']}",
            f"Address: {patient_context['address']['street']}, {patient_context['address']['city']}, {patient_context['address']['state']} {patient_context['address']['zip']}",
            f"Driver's License: {patient_context['drivers_license']}",
            f"Emergency Contact: {patient_context['emergency_contact']['name']} ({patient_context['emergency_contact']['relationship']}), Phone: {patient_context['emergency_contact']['phone']}",
            f"Insurance Provider: {patient_context['insurance']['provider']}",
            f"Insurance ID: {patient_context['insurance']['plan_id']}",
            f"Attending Provider: {patient_context['provider']['name']}",
            f"Provider Phone: {patient_context['provider']['phone']}",
            f"Provider Fax: {patient_context['provider']['fax']}",
            f"Facility: {patient_context['facility']['name']}",
            f"Facility Phone: {patient_context['facility']['phone']}",
            f"Encounter Date: {patient_context['encounter_date']}",
            f"Encounter DateTime: {patient_context['encounter_datetime']}",
        ]
        return "\n".join(lines)

    def _find_phi_positions(
        self,
        text: str,
        patient_context: dict
    ) -> List[PHIEntity]:
        """
        Find all PHI occurrences in the generated text with their positions.

        Args:
            text: The generated note text
            patient_context: The PHI values used to generate the note

        Returns:
            List of PHIEntity objects with positions
        """
        entities = []

        # Map of PHI values to their types
        phi_values = [
            (patient_context['full_name'], PHIType.NAME),
            (patient_context['first_name'], PHIType.NAME),
            (patient_context['last_name'], PHIType.NAME),
            (patient_context['dob'], PHIType.DATE),
            (patient_context['ssn'], PHIType.SSN),
            (patient_context['mrn'], PHIType.MRN),
            (patient_context['phone'], PHIType.PHONE),
            (patient_context['email'], PHIType.EMAIL),
            (patient_context['drivers_license'], PHIType.LICENSE),
            (patient_context['emergency_contact']['name'], PHIType.NAME),
            (patient_context['emergency_contact']['phone'], PHIType.PHONE),
            (patient_context['insurance']['plan_id'], PHIType.HEALTH_PLAN_ID),
            (patient_context['provider']['name'], PHIType.NAME),
            (patient_context['provider']['phone'], PHIType.PHONE),
            (patient_context['provider']['fax'], PHIType.FAX),
            (patient_context['facility']['name'], PHIType.OTHER),
            (patient_context['facility']['phone'], PHIType.PHONE),
            (patient_context['encounter_date'], PHIType.DATE),
            (patient_context['encounter_datetime'], PHIType.DATE),
            # Address components
            (patient_context['address']['street'], PHIType.ADDRESS),
            (patient_context['address']['city'], PHIType.ADDRESS),
            (patient_context['address']['state'], PHIType.ADDRESS),
            (patient_context['address']['zip'], PHIType.ADDRESS),
        ]

        # Find all occurrences of each PHI value
        for value, phi_type in phi_values:
            if not value or len(str(value)) < 2:  # Skip empty or very short values
                continue

            value_str = str(value)
            # Find all occurrences using regex for word boundary matching
            # Use re.escape to handle special characters in the value
            pattern = re.escape(value_str)
            for match in re.finditer(pattern, text):
                entities.append(PHIEntity(
                    phi_type=phi_type,
                    value=value_str,
                    start=match.start(),
                    end=match.end()
                ))

        # Sort by position
        entities.sort(key=lambda e: e.start)

        return entities

    def generate_note(
        self,
        note_type: NoteType,
        note_id: Optional[str] = None,
        patient_context: Optional[dict] = None,
        additional_context: Optional[dict] = None
    ) -> GeneratedNote:
        """
        Generate a clinical note with embedded PHI.

        Args:
            note_type: Type of clinical note to generate
            note_id: Optional ID for the note (auto-generated if not provided)
            patient_context: Optional pre-generated patient context
            additional_context: Optional additional context (e.g., chief complaint, diagnosis)

        Returns:
            GeneratedNote object with content and PHI manifest
        """
        # Generate note ID if not provided
        if note_id is None:
            prefix = note_type.value.upper()[:2]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            note_id = f"{prefix}_{timestamp}"

        # Generate patient context if not provided
        if patient_context is None:
            patient_context = self.phi_gen.generate_patient_context()

        # Add note-type-specific context
        if additional_context:
            patient_context.update(additional_context)

        # Load and populate prompt template
        prompt_template = self._load_prompt_template(note_type)
        phi_context = self._build_phi_context_string(patient_context)

        # Build the full prompt
        prompt = prompt_template.format(
            phi_context=phi_context,
            **patient_context
        )

        # Get system role based on note type
        system_roles = {
            NoteType.EMERGENCY_DEPT: "You are an emergency department physician documenting patient encounters.",
            NoteType.DISCHARGE_SUMMARY: "You are a hospitalist physician writing discharge summaries.",
            NoteType.PROGRESS_NOTE: "You are an internal medicine physician documenting daily progress notes.",
            NoteType.RADIOLOGY_REPORT: "You are a radiologist dictating imaging reports.",
            NoteType.TELEHEALTH_CONSULT: "You are a primary care physician conducting telehealth visits.",
        }
        system_role = system_roles.get(note_type, "You are a clinical documentation specialist.")

        # Generate the note using LLM
        generated_content = self.bedrock.generate(
            prompt=prompt,
            system_role=system_role,
            max_retries=self.config.max_retries,
            retry_delay_base=self.config.retry_delay_base
        )

        # Find PHI positions in generated content
        phi_entities = self._find_phi_positions(generated_content, patient_context)

        return GeneratedNote(
            note_id=note_id,
            note_type=note_type,
            content=generated_content,
            phi_entities=phi_entities
        )

    def save_note(self, note: GeneratedNote, output_dir: Optional[Path] = None):
        """
        Save a generated note and its manifest to files.

        Args:
            note: The generated note to save
            output_dir: Optional output directory (uses config default if not provided)
        """
        if output_dir is None:
            output_dir = self.config.output_dir

        notes_dir = output_dir / self.config.notes_subdir
        manifests_dir = output_dir / self.config.manifests_subdir

        notes_dir.mkdir(parents=True, exist_ok=True)
        manifests_dir.mkdir(parents=True, exist_ok=True)

        # Save note content
        note_path = notes_dir / f"{note.note_id}.txt"
        note_path.write_text(note.content)

        # Save manifest
        manifest_path = manifests_dir / f"{note.note_id}.json"
        manifest_path.write_text(json.dumps(note.to_manifest(), indent=2))

        print(f"Saved note: {note_path}")
        print(f"Saved manifest: {manifest_path}")

    def generate_and_save(
        self,
        note_type: NoteType,
        count: int = 1,
        output_dir: Optional[Path] = None
    ) -> List[GeneratedNote]:
        """
        Generate multiple notes of a given type and save them.

        Args:
            note_type: Type of notes to generate
            count: Number of notes to generate
            output_dir: Optional output directory

        Returns:
            List of generated notes
        """
        notes = []
        for i in range(count):
            print(f"Generating {note_type.value} note {i + 1}/{count}...")
            note = self.generate_note(note_type)
            self.save_note(note, output_dir)
            notes.append(note)

        return notes
