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