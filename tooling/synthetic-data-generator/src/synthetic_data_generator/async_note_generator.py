"""Async note generator with rate limiting for concurrent generation."""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from aiolimiter import AsyncLimiter
from tqdm.asyncio import tqdm

from .async_bedrock_client import AsyncBedrockClient
from .config import GeneratorConfig, DEFAULT_GENERATOR_CONFIG
from .fhir_parser import FHIRBundleParser
from .models.note_models import GeneratedNote, NoteType, PHIEntity, PHIType
from .phi_generator import PHIGenerator
from .phi_injector import PHIInjector
from .prompts import PROMPTS, TEMPLATE_MODE_PROMPT
from .note_generator import NoteGenerator


class AsyncNoteGenerator:
    """Orchestrates concurrent note generation with rate limiting."""

    def __init__(
        self,
        config: Optional[GeneratorConfig] = None,
        rate_limit: int = 150
    ):
        """
        Initialize async note generator.

        Args:
            config: Generator configuration
            rate_limit: Maximum requests per minute (default: 150)
        """
        self.config = config or DEFAULT_GENERATOR_CONFIG
        self.rate_limit = rate_limit
        self.limiter = AsyncLimiter(rate_limit, time_period=60)
        self.bedrock = AsyncBedrockClient()
        self.phi_gen = PHIGenerator()
        self.phi_injector = PHIInjector(phi_generator=self.phi_gen)

        # Reuse sync NoteGenerator for context building and PHI extraction
        self._sync_generator = NoteGenerator(config=self.config)

    async def generate_note(
        self,
        bundle_path: Path,
        note_type: NoteType,
        note_id: Optional[str] = None,
        template_mode: bool = False
    ) -> GeneratedNote:
        """
        Generate a single note with rate limiting.

        Args:
            bundle_path: Path to FHIR bundle JSON
            note_type: Type of note to generate
            note_id: Optional note ID (auto-generated if not provided)
            template_mode: Whether to generate template with placeholders

        Returns:
            GeneratedNote object
        """
        # Acquire rate limit token
        async with self.limiter:
            return await self._generate_note_internal(
                bundle_path=bundle_path,
                note_type=note_type,
                note_id=note_id,
                template_mode=template_mode
            )

    async def _generate_note_internal(
        self,
        bundle_path: Path,
        note_type: NoteType,
        note_id: Optional[str],
        template_mode: bool
    ) -> GeneratedNote:
        """Internal note generation logic."""
        # Generate note ID if not provided
        if note_id is None:
            prefix = note_type.value.upper()[:2]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            note_id = f"{prefix}_{timestamp}"

        # Build clinical limits from config
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

        # Parse FHIR bundle (sync - fast CPU operation)
        parser = FHIRBundleParser(bundle_path)
        context = parser.get_full_context()

        # Inject additional PHI
        context = self.phi_injector.inject(context)

        # Add encounter context
        encounters = context.get('encounters', [])
        encounter_index = self.config.encounter_index if self.config else -1
        current_encounter = (
            encounters[encounter_index]
            if (encounters and -1 <= encounter_index < len(encounters))
            else {}
        )
        context['current_encounter'] = current_encounter
        if current_encounter.get('start_datetime'):
            context['encounter_date'] = current_encounter['start_datetime'][:10]
            context['encounter_datetime'] = current_encounter['start_datetime']

        # Build PHI context string
        phi_context = self._sync_generator._build_phi_context_from_fhir(
            context, clinical_limits=clinical_limits
        )

        # Load prompt template
        prompt_template = self._load_prompt(note_type, template_mode)

        # Add template instructions if needed
        if template_mode:
            phi_context = self._add_template_instructions(phi_context)

        # Build full prompt
        prompt = f"{prompt_template}\n\nPHI Context:\n{phi_context}"

        # Get system role
        system_role = self._get_system_role(note_type)

        # Generate via async Bedrock client
        generated_content = await self.bedrock.generate(
            prompt=prompt,
            system_role=system_role
        )

        # Extract PHI positions or placeholders
        if template_mode:
            phi_entities = []
            placeholders = self._extract_placeholders(generated_content)
        else:
            phi_entities = self._sync_generator._find_phi_positions_fhir(
                generated_content, context
            )
            placeholders = []

        return GeneratedNote(
            note_id=note_id,
            note_type=note_type,
            content=generated_content,
            phi_entities=phi_entities,
            is_template=template_mode,
            placeholders=placeholders
        )

    async def generate_all(
        self,
        tasks: list[tuple[Path, NoteType]],
        template_mode: bool = False
    ) -> tuple[list[GeneratedNote], list[Exception]]:
        """
        Generate all notes concurrently with progress bar.

        Args:
            tasks: List of (bundle_path, note_type) tuples
            template_mode: Whether to generate templates

        Returns:
            Tuple of (successful_notes, errors)
        """
        async def generate_and_save(
            task: tuple[Path, NoteType],
            pbar: tqdm
        ) -> Union[GeneratedNote, Exception]:
            """Generate a note, save it, update progress, and return result or exception."""
            try:
                bundle_path, note_type = task
                note = await self.generate_note(
                    bundle_path=bundle_path,
                    note_type=note_type,
                    template_mode=template_mode
                )
                self._save_note(note)
                return note
            except Exception as e:
                return e
            finally:
                pbar.update(1)

        # Run all tasks concurrently with progress bar
        notes = []
        errors = []

        with tqdm(total=len(tasks), desc="Generating notes", unit="note") as pbar:
            # Create tasks with progress bar reference
            coroutines = [generate_and_save(task, pbar) for task in tasks]

            # Run concurrently using asyncio.gather
            results = await asyncio.gather(*coroutines)

            # Separate successes from errors
            for result in results:
                if isinstance(result, Exception):
                    errors.append(result)
                else:
                    notes.append(result)

        return notes, errors

    def _save_note(self, note: GeneratedNote) -> None:
        """Save note and manifest to disk."""
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

    def _load_prompt(self, note_type: NoteType, template_mode: bool) -> str:
        """Load prompt for note type."""
        if note_type not in PROMPTS:
            raise ValueError(f"No prompt found for note type: {note_type}")

        prompt = PROMPTS.get(note_type)
        if template_mode:
            prompt += "\n\n" + TEMPLATE_MODE_PROMPT
        return prompt

    def _get_system_role(self, note_type: NoteType) -> str:
        """Get system role for note type."""
        roles = {
            NoteType.EMERGENCY_DEPT: "You are an emergency department physician documenting patient encounters.",
            NoteType.DISCHARGE_SUMMARY: "You are a hospitalist physician writing discharge summaries.",
            NoteType.PROGRESS_NOTE: "You are an internal medicine physician documenting daily progress notes.",
            NoteType.RADIOLOGY_REPORT: "You are a radiologist dictating imaging reports.",
            NoteType.TELEHEALTH_CONSULT: "You are a primary care physician conducting telehealth visits.",
        }
        return roles.get(note_type, "You are a clinical documentation specialist.")

    def _add_template_instructions(self, phi_context: str) -> str:
        """Add template placeholder instructions to context."""
        instructions = """
IMPORTANT: Generate this note as a TEMPLATE with placeholders instead of actual PHI values.
Use these exact placeholder formats:
- {{NAME}} for patient name
- {{DOB}} for date of birth
- {{MRN}} for Medical Record Number
- {{PHONE}} for phone numbers
- {{EMAIL}} for email addresses
- {{ADDRESS}} for street address
- {{DATE}} for dates

Use the clinical context as-is, but replace all PHI with placeholders.
"""
        return instructions + "\n\nReference PHI:\n" + phi_context

    def _extract_placeholders(self, text: str) -> list[str]:
        """Extract unique placeholder names from template text."""
        pattern = r'\{\{([A-Z_]+)\}\}'
        matches = re.findall(pattern, text)
        return list(set(matches))
