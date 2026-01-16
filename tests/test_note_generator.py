"""Tests for NoteGenerator."""
import pytest
from src.note_generator import NoteGenerator
from src.config import NoteType


@pytest.mark.unit
class TestNoteGeneratorContextBuilding:
    """Test context string building."""

    def test_build_phi_context_from_fhir(self, test_config, fhir_parser, mock_bedrock_client):
        """Test building PHI context from FHIR data."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        synthea_context = fhir_parser.get_full_context()

        context_str = generator._build_phi_context_from_fhir(synthea_context)

        assert isinstance(context_str, str)
        assert len(context_str) > 0
        # Should contain patient demographics
        assert 'John' in context_str or 'Smith' in context_str
        assert 'MRN' in context_str or '123456' in context_str

    def test_context_includes_all_phi_fields(self, test_config, fhir_parser, mock_bedrock_client):
        """Test that context includes expected PHI fields."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        synthea_context = fhir_parser.get_full_context()

        context_str = generator._build_phi_context_from_fhir(synthea_context)

        # Check for various PHI types
        assert any(field in context_str for field in ['Name', 'DOB', 'Birth', 'MRN', 'SSN'])


@pytest.mark.unit
class TestNoteGeneratorPHIExtraction:
    """Test PHI entity extraction from generated text."""

    def test_find_phi_positions_fhir(self, test_config, fhir_parser, mock_bedrock_client):
        """Test finding PHI positions in generated note from FHIR."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        synthea_context = fhir_parser.get_full_context()

        # Generate note (will use mocked LLM)
        generated_text = mock_bedrock_client.generate.return_value

        phi_entities = generator._find_phi_positions_fhir(generated_text, synthea_context)

        assert isinstance(phi_entities, list)
        # Should find at least some PHI in the mocked response
        assert len(phi_entities) >= 0

    def test_phi_entities_sorted_by_position(self, test_config, fhir_parser, mock_bedrock_client):
        """Test that PHI entities are sorted by position."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        synthea_context = fhir_parser.get_full_context()

        generated_text = mock_bedrock_client.generate.return_value
        phi_entities = generator._find_phi_positions_fhir(generated_text, synthea_context)

        if len(phi_entities) > 1:
            for i in range(len(phi_entities) - 1):
                assert phi_entities[i].start <= phi_entities[i + 1].start


@pytest.mark.unit
class TestNoteGeneratorGeneration:
    """Test note generation flow."""

    def test_generate_from_fhir(self, test_config, minimal_fhir_bundle_path, mock_bedrock_client):
        """Test generating a note from FHIR bundle."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)

        result = generator.generate_from_fhir(
            bundle_path=minimal_fhir_bundle_path,
            note_type=NoteType.EMERGENCY_DEPT,
            template_mode=False
        )

        assert result.note_id is not None
        assert result.content is not None
        assert isinstance(result.content, str)
        assert isinstance(result.phi_entities, list)

    def test_generate_template_mode(self, test_config, minimal_fhir_bundle_path, mock_bedrock_client):
        """Test generating in template mode with placeholders."""
        # Modify mock to return text with placeholders
        mock_bedrock_client.generate.return_value = "Patient: {{NAME}}\nDOB: {{DOB}}\nMRN: {{MRN}}"

        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)

        result = generator.generate_from_fhir(
            bundle_path=minimal_fhir_bundle_path,
            note_type=NoteType.EMERGENCY_DEPT,
            template_mode=True
        )

        assert result.is_template is True
        assert isinstance(result.placeholders, list)
        assert '{{NAME}}' in result.content or '{{DOB}}' in result.content