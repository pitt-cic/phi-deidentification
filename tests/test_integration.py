"""Integration tests for end-to-end flows."""
import pytest
from pathlib import Path

from src.fhir_parser import FHIRBundleParser
from src.phi_injector import PHIInjector
from src.note_generator import NoteGenerator
from src.config import NoteType


@pytest.mark.integration
class TestHappyPathFHIRGeneration:
    """Test complete flow from FHIR to generated note."""

    def test_fhir_to_note_complete_flow(
        self, test_config, minimal_fhir_bundle_path, mock_bedrock_client
    ):
        """Test complete flow: FHIR → context → injector → LLM → PHI extraction → result."""
        # Step 1: Parse FHIR bundle
        parser = FHIRBundleParser(minimal_fhir_bundle_path)
        synthea_context = parser.get_full_context()

        # Step 2: Inject additional PHI
        injector = PHIInjector()
        enhanced_context = injector.inject(synthea_context)

        # Step 3: Generate note
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        result = generator.generate_from_fhir(
            bundle_path=minimal_fhir_bundle_path,
            note_type=NoteType.EMERGENCY_DEPT,
            template_mode=False
        )

        # Verify result
        assert hasattr(result, 'content')
        assert hasattr(result, 'phi_entities')
        assert len(result.content) > 0

    def test_context_passes_through_correctly(
        self, test_config, minimal_fhir_bundle_path, mock_bedrock_client
    ):
        """Test that context data flows through the pipeline correctly."""
        parser = FHIRBundleParser(minimal_fhir_bundle_path)
        synthea_context = parser.get_full_context()

        # Verify patient data exists
        assert 'patient' in synthea_context
        assert 'first_name' in synthea_context['patient']

        # Inject PHI
        injector = PHIInjector()
        enhanced_context = injector.inject(synthea_context)

        # Verify injection preserved original data and added new fields
        assert enhanced_context['patient']['first_name'] == synthea_context['patient']['first_name']
        assert 'email' in enhanced_context['patient']  # New injected field


@pytest.mark.integration
@pytest.mark.parametrize("note_type", [
    NoteType.EMERGENCY_DEPT,
    NoteType.PROGRESS_NOTE,
    NoteType.DISCHARGE_SUMMARY,
    NoteType.RADIOLOGY_REPORT,
    NoteType.TELEHEALTH_CONSULT
])
class TestAllNoteTypes:
    """Test generation for all note types."""

    def test_generate_all_note_types(
        self, test_config, minimal_fhir_bundle_path, mock_bedrock_client, note_type
    ):
        """Test that all note types can be generated."""
        parser = FHIRBundleParser(minimal_fhir_bundle_path)
        synthea_context = parser.get_full_context()

        injector = PHIInjector()
        enhanced_context = injector.inject(synthea_context)

        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        result = generator.generate_from_fhir(
            bundle_path=minimal_fhir_bundle_path,
            note_type=note_type,
            template_mode=False
        )

        assert hasattr(result, 'content')
        assert len(result.content) > 0
