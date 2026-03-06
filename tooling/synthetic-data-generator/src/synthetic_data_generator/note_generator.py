"""Clinical note generator using LLM with PHI injection."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bedrock_client import BedrockClient
from .config import (
    DEFAULT_GENERATOR_CONFIG,
    GeneratorConfig,
)
from .fhir_parser import FHIRBundleParser
from .models.note_models import GeneratedNote, NoteType, PHIEntity, PHIType
from .phi_generator import PHIGenerator
from .phi_injector import PHIInjector
from .s3_client import S3Client
from .utils import parse_s3_path
from .prompts import PROMPTS, TEMPLATE_MODE_PROMPT


class NoteGenerator:
    """Generate clinical notes with embedded PHI using LLM."""

    def __init__(
        self,
        bedrock_client: Optional[BedrockClient] = None,
        s3_client: Optional[S3Client] = None,
        phi_generator: Optional[PHIGenerator] = None,
        config: Optional[GeneratorConfig] = None
    ):
        self.bedrock = bedrock_client or BedrockClient()
        self.s3_client = s3_client or S3Client()
        self.phi_gen = phi_generator or PHIGenerator()
        self.phi_injector = PHIInjector(phi_generator=self.phi_gen)
        self.config = config or DEFAULT_GENERATOR_CONFIG

    def _load_prompt(self, note_type: NoteType, template_mode: bool = False) -> str:
        """Load a prompt for the given note type."""
        if note_type not in PROMPTS:
            raise ValueError(f"No prompt found for note type: {note_type}")
        
        prompt = PROMPTS.get(note_type)

        if template_mode:
            prompt += "\n\n" + TEMPLATE_MODE_PROMPT

        return prompt

    def _build_phi_context_from_fhir(
        self,
        fhir_context: Dict[str, Any],
        clinical_limits: Optional[Dict[str, Optional[int]]] = None
    ) -> str:
        """
        Build PHI context string from FHIR data using dataclass methods.

        Args:
            fhir_context: Full context from FHIRBundleParser
            clinical_limits: Optional dict of clinical limits (max_conditions, max_medications, etc.)

        Returns:
            Formatted context string for LLM
        """
        from .fhir_parser import (
            ClinicalContext,
            EncounterData,
            PatientData,
            ProviderData,
        )

        sections = []

        # Patient Information
        if 'patient' in fhir_context and fhir_context['patient']:
            patient = fhir_context['patient']

            # Convert dict to PatientData if needed
            if isinstance(patient, dict):
                patient_obj = PatientData(**patient)
            else:
                patient_obj = patient

            patient_context = patient_obj.to_context_string()
            if patient_context:
                sections.append("## Patient Information")
                sections.append(patient_context)

        # Clinical Context
        if 'clinical' in fhir_context and fhir_context['clinical']:
            clinical = fhir_context['clinical']

            # Convert dict to ClinicalContext if needed
            if isinstance(clinical, dict):
                clinical_obj = ClinicalContext(**clinical)
            else:
                clinical_obj = clinical

            # Pass individual limits to to_context_string
            clinical_context = clinical_obj.to_context_string(
                max_conditions=clinical_limits.get('max_conditions') if clinical_limits else None,
                max_medications=clinical_limits.get('max_medications') if clinical_limits else None,
                max_procedures=clinical_limits.get('max_procedures') if clinical_limits else None,
                max_allergies=clinical_limits.get('max_allergies') if clinical_limits else None,
                max_immunizations=clinical_limits.get('max_immunizations') if clinical_limits else None,
                max_observations=clinical_limits.get('max_observations') if clinical_limits else None,
                max_imaging_studies=clinical_limits.get('max_imaging_studies') if clinical_limits else None,
                max_devices=clinical_limits.get('max_devices') if clinical_limits else None
            )
            if clinical_context:
                sections.append(clinical_context)

        # Provider Information
        if 'providers' in fhir_context and fhir_context['providers']:
            sections.append("## Provider Information")

            for provider_data in fhir_context['providers']:
                if isinstance(provider_data, dict):
                    provider_obj = ProviderData(**provider_data)
                else:
                    provider_obj = provider_data

                provider_context = provider_obj.to_context_string()
                if provider_context:
                    sections.append(provider_context)
                    sections.append("")  # Blank line between providers

        # Encounter Information (if present)
        if 'encounters' in fhir_context and fhir_context['encounters']:
            sections.append("## Encounter Information")

            for encounter_data in fhir_context['encounters']:
                if isinstance(encounter_data, dict):
                    encounter_obj = EncounterData(**encounter_data)
                else:
                    encounter_obj = encounter_data

                encounter_context = encounter_obj.to_context_string()
                if encounter_context:
                    sections.append(encounter_context)
                    sections.append("")  # Blank line between encounters

        return "\n\n".join(sections)

    def _build_phi_context_from_faker(self, patient_context: dict) -> str:
        """Build PHI context string from Faker-generated data."""
        lines = [
            f"Patient Name: {patient_context.get('full_name', '')}",
            f"Date of Birth: {patient_context.get('dob', '')}",
            f"Age: {patient_context.get('age', '')} years old",
            f"Gender: {patient_context.get('gender', '')}",
            f"SSN: {patient_context.get('ssn', '')}",
            f"MRN: {patient_context.get('mrn', '')}",
            f"Phone: {patient_context.get('phone', '')}",
            f"Email: {patient_context.get('email', '')}",
        ]

        # Handle nested address
        if 'address' in patient_context and isinstance(patient_context['address'], dict):
            addr = patient_context['address']
            lines.append(f"Address: {addr.get('street', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zip', '')}")
        else:
            lines.append(f"Address: {patient_context.get('full_address', '')}")

        lines.extend([
            f"Driver's License: {patient_context.get('drivers_license', '')}",
            f"Emergency Contact: {patient_context.get('emergency_contact', {}).get('name', '')} ({patient_context.get('emergency_contact', {}).get('relationship', '')}), Phone: {patient_context.get('emergency_contact', {}).get('phone', '')}",
            f"Insurance Provider: {patient_context.get('insurance', {}).get('provider', '')}",
            f"Insurance ID: {patient_context.get('insurance', {}).get('plan_id', '')}",
            f"Attending Provider: {patient_context.get('provider', {}).get('name', '')}",
            f"Provider Phone: {patient_context.get('provider', {}).get('phone', '')}",
            f"Provider Fax: {patient_context.get('provider', {}).get('fax', '')}",
            f"Facility: {patient_context.get('facility', {}).get('name', '')}",
            f"Facility Phone: {patient_context.get('facility', {}).get('phone', '')}",
            f"Encounter Date: {patient_context.get('encounter_date', '')}",
            f"Encounter DateTime: {patient_context.get('encounter_datetime', '')}",
        ])
        return "\n".join(lines)

    def _find_phi_positions_fhir(self, text: str, context: Dict[str, Any]) -> List[PHIEntity]:
        """Find PHI positions in text using FHIR-extracted context."""
        entities = []
        patient = context.get('patient', {})
        # providers = context.get('providers', [{}])
        # provider = providers[0] if providers else {}
        facility = context.get('facility', {})
        device = context.get('device', {})

        # Build a list of PHI values to search for
        phi_values = [
            (patient.get("prefix", ""), PHIType.NAME),
            (patient.get("full_name", ""), PHIType.NAME),
            (patient.get("first_name", ""), PHIType.NAME),
            (patient.get("last_name", ""), PHIType.NAME),
            (patient.get("birth_date", ""), PHIType.DATE),
            (patient.get("ssn", ""), PHIType.SSN),
            (patient.get("mrn", ""), PHIType.MRN),
            (patient.get("phone", ""), PHIType.PHONE),
            (patient.get("email", ""), PHIType.EMAIL),
            (patient.get("drivers_license", ""), PHIType.LICENSE),
            (patient.get("passport", ""), PHIType.OTHER),
            (patient.get("full_address", ""), PHIType.ADDRESS),
            (patient.get("address_city_and_state", ""), PHIType.ADDRESS),
            (patient.get("address_state_and_country", ""), PHIType.ADDRESS),
            (patient.get("address_city_state_and_country", ""), PHIType.ADDRESS),
            (patient.get("address_line", ""), PHIType.ADDRESS),
            (patient.get("city", ""), PHIType.ADDRESS),
            (patient.get("state", ""), PHIType.ADDRESS),
            (patient.get("zip_code", ""), PHIType.ADDRESS),
            (patient.get("health_plan_id", ""), PHIType.HEALTH_PLAN_ID),
            (patient.get("account_number", ""), PHIType.ACCOUNT_NUMBER),
            (patient.get("vehicle_id", ""), PHIType.VEHICLE_ID),
            (patient.get("license_plate", ""), PHIType.VEHICLE_ID),
            (patient.get("ip_address", ""), PHIType.IP_ADDRESS),
            (patient.get("patient_portal_url", ""), PHIType.URL),
            (patient.get("emergency_contact_name", ""), PHIType.NAME),
            (patient.get("emergency_contact_phone", ""), PHIType.PHONE),
            (patient.get("birth_city_and_state", ""), PHIType.ADDRESS),
            (patient.get("birth_state_and_country", ""), PHIType.ADDRESS),
            (patient.get("birth_city_state_and_country", ""), PHIType.ADDRESS),
            (patient.get("birth_city", ""), PHIType.ADDRESS),
            (patient.get("birth_state", ""), PHIType.ADDRESS),
            (patient.get("birth_country", ""), PHIType.ADDRESS),
            (patient.get('mothers_maiden_name', ''), PHIType.NAME),
            # (provider.get('name', ''), PHIType.NAME),
            # (provider.get('phone', ''), PHIType.PHONE),
            # (provider.get('fax', ''), PHIType.FAX),
            (facility.get("name", ""), PHIType.OTHER),
            (facility.get("phone", ""), PHIType.PHONE),
            (facility.get("fax", ""), PHIType.FAX),
            (device.get('id', ''), PHIType.DEVICE_ID),
        ]

        # Add encounter dates from encounters
        for enc in context.get('encounters', []):
            if enc.get('start_datetime'):
                phi_values.append((enc['start_datetime'][:10], PHIType.DATE))
            if enc.get('end_datetime'):
                phi_values.append((enc['end_datetime'][:10], PHIType.DATE))
            if enc.get('location_name'):
                phi_values.append((enc['location_name'], PHIType.OTHER))
            if enc.get('provider_name'):
                phi_values.append((enc['provider_name'], PHIType.OTHER))
            if enc.get('primary_practitioner'):
                phi_values.append((enc['primary_practitioner'], PHIType.NAME))

        # Find all occurrences
        for value, phi_type in phi_values:
            if not value or len(str(value)) < 2:
                continue
            value_str = str(value)
            # Use word boundaries to prevent substring matches (e.g., "PA" in "patient")
            pattern = r'(?<!\w)' + re.escape(value_str) + r'(?!\w)'
            for match in re.finditer(pattern, text):
                entities.append(PHIEntity(
                    phi_type=phi_type,
                    value=value_str,
                    start=match.start(),
                    end=match.end()
                ))

        entities.sort(key=lambda e: e.start)
        return entities

    def _find_phi_positions_faker(self, text: str, patient_context: dict) -> List[PHIEntity]:
        """Find PHI positions in text using Faker-generated context."""
        entities = []

        phi_values = [
            (patient_context.get('full_name', ''), PHIType.NAME),
            (patient_context.get('first_name', ''), PHIType.NAME),
            (patient_context.get('last_name', ''), PHIType.NAME),
            (patient_context.get('nicknames', ''), PHIType.NAME),
            (patient_context.get('birth_date', ''), PHIType.DATE),
            (patient_context.get('ssn', ''), PHIType.SSN),
            (patient_context.get('mrn', ''), PHIType.MRN),
            (patient_context.get('phone', ''), PHIType.PHONE),
            (patient_context.get('email', ''), PHIType.EMAIL),
            (patient_context.get('drivers_license', ''), PHIType.LICENSE),
            (patient_context.get('passport', ''), PHIType.OTHER),
            (patient_context.get('emergency_contact', {}).get('name', ''), PHIType.NAME),
            (patient_context.get('emergency_contact', {}).get('phone', ''), PHIType.PHONE),
            (patient_context.get('insurance', {}).get('plan_id', ''), PHIType.HEALTH_PLAN_ID),
            (patient_context.get('provider', {}).get('name', ''), PHIType.NAME),
            (patient_context.get('provider', {}).get('phone', ''), PHIType.PHONE),
            (patient_context.get('provider', {}).get('fax', ''), PHIType.FAX),
            (patient_context.get('facility', {}).get('name', ''), PHIType.OTHER),
            (patient_context.get('facility', {}).get('phone', ''), PHIType.PHONE),
            (patient_context.get('encounter_date', ''), PHIType.DATE),
            (patient_context.get('encounter_datetime', ''), PHIType.DATE),
        ]

        # Handle nested address
        if 'address' in patient_context and isinstance(patient_context['address'], dict):
            addr = patient_context['address']
            phi_values.extend([
                (addr.get('street', ''), PHIType.ADDRESS),
                (addr.get('city', ''), PHIType.ADDRESS),
                (addr.get('state', ''), PHIType.ADDRESS),
                (addr.get('zip', ''), PHIType.ADDRESS),
            ])

        for value, phi_type in phi_values:
            if not value or len(str(value)) < 2:
                continue
            value_str = str(value)
            # Use word boundaries to prevent substring matches (e.g., "PA" in "patient")
            pattern = r'(?<!\w)' + re.escape(value_str) + r'(?!\w)'
            for match in re.finditer(pattern, text):
                entities.append(PHIEntity(
                    phi_type=phi_type,
                    value=value_str,
                    start=match.start(),
                    end=match.end()
                ))

        entities.sort(key=lambda e: e.start)
        return entities

    def generate_from_fhir(
        self,
        bundle_path: Path,
        note_type: NoteType,
        note_id: Optional[str] = None,
        template_mode: bool = False,
        encounter_index: Optional[int] = None
    ) -> GeneratedNote:
        """
        Generate a clinical note from a FHIR bundle.

        Args:
            bundle_path: Path to the FHIR bundle JSON file
            note_type: Type of clinical note to generate
            note_id: Optional ID for the note
            template_mode: If True, generate template with {{PLACEHOLDERS}}
            encounter_index: Which encounter to use (None = use config, -1 = most recent, 0+ = specific)

        Returns:
            GeneratedNote object
        """
        # Use config default if encounter_index not specified
        if encounter_index is None:
            encounter_index = self.config.encounter_index if self.config else -1

        # Build clinical limits dict from config
        clinical_limits = None
        if self.config:
            clinical_limits = {
                'max_conditions': self.config.max_conditions,
                'max_medications': self.config.max_medications,
                'max_procedures': self.config.max_procedures,
                'max_allergies': self.config.max_allergies,
                'max_immunizations': self.config.max_immunizations,
                'max_observations': self.config.max_observations,
                'max_imaging_studies': self.config.max_imaging_studies,
                'max_devices': self.config.max_devices,
            }

        # Parse FHIR bundle
        parser = FHIRBundleParser(bundle_path)
        context = parser.get_full_context()

        # Inject additional PHI not in Synthea
        context = self.phi_injector.inject(context)

        # Add encounter-specific context
        encounters = context.get('encounters', [])
        current_encounter = (
            encounters[encounter_index]
            if (encounters and -1 <= encounter_index < len(encounters))
            else {}
        )
        context['current_encounter'] = current_encounter
        if current_encounter.get('start_datetime'):
            context['encounter_date'] = current_encounter['start_datetime'][:10]
            context['encounter_datetime'] = current_encounter['start_datetime']

        # Inject additional PHI not in Synthea
        context = self.phi_injector.inject(context)

        return self._generate_note_internal(
            note_type=note_type,
            note_id=note_id,
            context=context,
            template_mode=template_mode,
            context_type='fhir',
            clinical_limits=clinical_limits
        )

    def generate_from_faker(
        self,
        note_type: NoteType,
        note_id: Optional[str] = None,
        template_mode: bool = False
    ) -> GeneratedNote:
        """
        Generate a clinical note using Faker-generated PHI.

        Args:
            note_type: Type of clinical note to generate
            note_id: Optional ID for the note
            template_mode: If True, generate template with {{PLACEHOLDERS}}

        Returns:
            GeneratedNote object
        """
        patient_context = self.phi_gen.generate_patient_context()
        return self._generate_note_internal(
            note_type=note_type,
            note_id=note_id,
            context=patient_context,
            template_mode=template_mode,
            context_type='faker'
        )

    def _generate_note_internal(
        self,
        note_type: NoteType,
        note_id: Optional[str],
        context: Dict[str, Any],
        template_mode: bool,
        context_type: str,
        clinical_limits: Optional[Dict[str, Optional[int]]] = None
    ) -> GeneratedNote:
        """Internal method to generate a note."""
        # Generate note ID if not provided
        if note_id is None:
            prefix = note_type.value.upper()[:2]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            note_id = f"{prefix}_{timestamp}"

        # Build PHI context string based on context type
        if context_type == 'fhir':
            phi_context = self._build_phi_context_from_fhir(context, clinical_limits=clinical_limits)
        else:
            phi_context = self._build_phi_context_from_faker(context)

        # Load prompt template
        prompt_template = self._load_prompt(note_type, template_mode)

        # Add template instructions if in template mode
        if template_mode:
            template_instructions = """
IMPORTANT: Generate this note as a TEMPLATE with placeholders instead of actual PHI values.
Use these exact placeholder formats:
- {{NAME}} for patient name
- {{FIRST_NAME}} for first name only
- {{LAST_NAME}} for last name only
- {{DOB}} for date of birth
- {{AGE}} for age
- {{GENDER}} for gender
- {{SSN}} for Social Security Number
- {{MRN}} for Medical Record Number
- {{PHONE}} for phone numbers
- {{FAX}} for fax numbers
- {{EMAIL}} for email addresses
- {{ADDRESS}} for street address
- {{CITY}} for city
- {{STATE}} for state
- {{ZIP}} for ZIP code
- {{DRIVERS_LICENSE}} for driver's license
- {{HEALTH_PLAN_ID}} for insurance ID
- {{ACCOUNT_NUMBER}} for account numbers
- {{EMERGENCY_CONTACT_NAME}} for emergency contact name
- {{EMERGENCY_CONTACT_PHONE}} for emergency contact phone
- {{PROVIDER_NAME}} for provider name
- {{PROVIDER_PHONE}} for provider phone
- {{PROVIDER_FAX}} for provider fax
- {{FACILITY_NAME}} for facility name
- {{FACILITY_PHONE}} for facility phone
- {{DATE}} for dates
- {{DEVICE_ID}} for device identifiers
- {{IP_ADDRESS}} for IP addresses
- {{URL}} for URLs

Use the clinical context (conditions, procedures, medications) as-is, but replace all PHI with placeholders.
"""
            phi_context = template_instructions + "\n\nReference PHI (for context only, use placeholders in output):\n" + phi_context

        # Build prompt
        prompt = f"{prompt_template}\n\nPHI Context:\n{phi_context}"

        # Get system role
        system_roles = {
            NoteType.EMERGENCY_DEPT: "You are an emergency department physician documenting patient encounters.",
            NoteType.DISCHARGE_SUMMARY: "You are a hospitalist physician writing discharge summaries.",
            NoteType.PROGRESS_NOTE: "You are an internal medicine physician documenting daily progress notes.",
            NoteType.RADIOLOGY_REPORT: "You are a radiologist dictating imaging reports.",
            NoteType.TELEHEALTH_CONSULT: "You are a primary care physician conducting telehealth visits.",
        }
        system_role = system_roles.get(note_type, "You are a clinical documentation specialist.")

        # Generate note
        generated_content = self.bedrock.generate(
            prompt=prompt,
            system_role=system_role
        )

        # Find PHI positions (or placeholders if template mode)
        if template_mode:
            phi_entities = []
            placeholders = self._extract_placeholders(generated_content)
        else:
            if context_type == 'fhir':
                phi_entities = self._find_phi_positions_fhir(generated_content, context)
            else:
                phi_entities = self._find_phi_positions_faker(generated_content, context)
            placeholders = []

        return GeneratedNote(
            note_id=note_id,
            note_type=note_type,
            content=generated_content,
            phi_entities=phi_entities,
            is_template=template_mode,
            placeholders=placeholders
        )

    def _extract_placeholders(self, text: str) -> List[str]:
        """Extract unique placeholder names from template text."""
        pattern = r'\{\{([A-Z_]+)\}\}'
        matches = re.findall(pattern, text)
        return list(set(matches))

    # Legacy method for backwards compatibility
    def generate_note(
        self,
        note_type: NoteType,
        note_id: Optional[str] = None,
        patient_context: Optional[dict] = None,
        additional_context: Optional[dict] = None
    ) -> GeneratedNote:
        """Generate a clinical note (legacy interface, uses Faker)."""
        if patient_context is None:
            patient_context = self.phi_gen.generate_patient_context()
        if additional_context:
            patient_context.update(additional_context)

        return self._generate_note_internal(
            note_type=note_type,
            note_id=note_id,
            context=patient_context,
            template_mode=False,
            context_type='faker'
        )

    def save_note(self, note: GeneratedNote):
        """Save a generated note and its manifest to files."""
        if note.is_template:
            notes_dir = self.config.template_notes_dir
            manifests_dir = self.config.template_manifests_dir
        else:
            notes_dir = self.config.notes_dir
            manifests_dir = self.config.manifests_dir

        # Save note content
        note_path = notes_dir / f"{note.note_id}.txt"
        note_path.write_text(note.content)

        # Save manifest
        manifest_path = manifests_dir / f"{note.note_id}.json"
        manifest_path.write_text(json.dumps(note.to_manifest(), indent=2))

        print(f"Saved note: {note_path}")
        print(f"Saved manifest: {manifest_path}")

        if self.config.s3_output_path:
            bucket, prefix = parse_s3_path(self.config.s3_output_path)
            if note.is_template:
                note_s3_key = f"{prefix}/{self.config.templates_subdir}/{self.config.notes_subdir}/{note_path.name}"
                manifest_s3_key = f"{prefix}/{self.config.templates_subdir}/{self.config.manifests_subdir}/{manifest_path.name}"
            else:
                note_s3_key = f"{prefix}/{self.config.notes_subdir}/{note_path.name}"
                manifest_s3_key = f"{prefix}/{self.config.manifests_subdir}/{manifest_path.name}"

            self.s3_client.upload(bucket, note_s3_key, note_path)
            print(f"Uploaded note to s3://{bucket}/{note_s3_key}")

            self.s3_client.upload(bucket, manifest_s3_key, manifest_path)
            print(f"Uploaded manifest to s3://{bucket}/{manifest_s3_key}")

    def generate_and_save(
        self,
        note_type: NoteType,
        count: int = 1,
        bundle_path: Optional[Path] = None,
        template_mode: bool = False
    ) -> List[GeneratedNote]:
        """
        Generate multiple notes of a given type and save them.

        Args:
            note_type: Type of notes to generate
            count: Number of notes to generate
            bundle_path: Optional FHIR bundle to use (uses Faker if not provided)
            template_mode: If True, generate templates

        Returns:
            List of generated notes
        """
        notes = []
        for i in range(count):
            print(f"Generating {note_type.value} {'template' if template_mode else 'note'} {i + 1}/{count}...")

            if bundle_path:
                note = self.generate_from_fhir(
                    bundle_path=bundle_path,
                    note_type=note_type,
                    template_mode=template_mode
                )
            else:
                note = self.generate_from_faker(
                    note_type=note_type,
                    template_mode=template_mode
                )

            self.save_note(note)
            notes.append(note)

        return notes
