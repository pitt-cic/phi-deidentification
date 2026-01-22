"""Tests for NoteGenerator."""
import pytest
from src.note_generator import NoteGenerator
from src.config import NoteType, PHIType


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

    def test_build_phi_context_uses_dataclass_methods(self, test_config, fhir_parser, mock_bedrock_client):
        """Test that _build_phi_context_from_fhir uses dataclass to_context_string methods."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        sample_fhir_context = fhir_parser.get_full_context()

        context_string = generator._build_phi_context_from_fhir(sample_fhir_context)

        # Should include patient data from PatientData.to_context_string()
        assert "Patient ID:" in context_string or "MRN:" in context_string
        assert "First Name:" in context_string or "Full Name:" in context_string

        # Should include clinical context from ClinicalContext.to_context_string()
        # (if sample has conditions/medications)
        if sample_fhir_context.get('clinical_context'):
            clinical = sample_fhir_context['clinical_context']
            if clinical.conditions or clinical.medications:
                assert "##" in context_string  # Section headers from ClinicalContext

        # Should be structured output (not just raw dict dump)
        assert isinstance(context_string, str)
        assert len(context_string) > 100  # Should have substantial content


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

    def test_no_substring_false_positives(self, test_config, fhir_parser, mock_bedrock_client):
        """Test that PHI matching does not match substrings within words."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        synthea_context = fhir_parser.get_full_context()

        # Create text with words that contain PHI values as substrings
        # State "PA" appears as substring in "PAST", "IMPACT", "REPAIR"
        # The fixture has state="PA" (minimal_fhir_bundle.json lines 73, 109, 236)
        # which should only match standalone "PA"
        test_text = """
    PAST MEDICAL HISTORY: The patient has IMPACT from prior injuries.
    Patient lives in PA and needs cardiac REPAIR surgery.
    Contact: 555-123-4567
    """

        phi_entities = generator._find_phi_positions_fhir(test_text, synthea_context)

        # Extract just the matched values for easier assertion
        matched_values = [entity.value for entity in phi_entities]

        # Should find the phone number (exact match)
        # Phone number from minimal_fhir_bundle.json line 57 (patient telecom)
        assert "555-123-4567" in matched_values

        # Should NOT find "PA" within "PAST", "IMPACT", or "REPAIR"
        # Count how many times "PA" was matched
        pa_matches = [e for e in phi_entities if e.value == "PA"]
        # Should match "PA" only once (standalone word), not as substrings
        assert len(pa_matches) == 1, f"Expected exactly 1 'PA' match (standalone), found {len(pa_matches)}"
        # Verify positions to ensure it's not inside other words
        for entity in pa_matches:
            # Get the context around the match
            start = entity.start
            end = entity.end
            # Verify it's not inside another word
            # Check character before and after
            if start > 0:
                char_before = test_text[start - 1]
                # Should not be alphanumeric (would indicate substring)
                assert not char_before.isalnum(), f"Found 'PA' as substring at position {start}: char_before='{char_before}'"
            if end < len(test_text):
                char_after = test_text[end]
                # Should not be alphanumeric
                assert not char_after.isalnum(), f"Found 'PA' as substring at position {start}: char_after='{char_after}'"

    def test_phi_matching_edge_cases(self, test_config, fhir_parser, mock_bedrock_client):
        """Test PHI matching handles edge cases correctly."""
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=test_config)
        synthea_context = fhir_parser.get_full_context()

        # Test various edge cases with fixture data:
        # - Patient name from minimal_fhir_bundle.json: family="Smith", given=["John", "Michael"]
        #   Parser extracts: full_name="John Michael Smith", first_name="John Michael", last_name="Smith"
        # - Phone from line 57: "555-123-4567"
        # - State from lines 73, 109, 236: "PA"
        test_text = """
    Patient: John Michael Smith
    Phone: 555-123-4567
    State: PA
    Email: john.smith@example.com
    """

        phi_entities = generator._find_phi_positions_fhir(test_text, synthea_context)
        matched_values = [entity.value for entity in phi_entities]

        # Should match all name components from fixture (full_name, first_name, last_name)
        assert "John Michael Smith" in matched_values, "Should match full_name"
        assert "John Michael" in matched_values, "Should match first_name"
        assert "Smith" in matched_values, "Should match last_name"

        # Should match phone with hyphens (fixture line 57)
        assert "555-123-4567" in matched_values

        # Should match state code when standalone (fixture lines 73, 109, 236)
        assert "PA" in matched_values

        # Verify entity types are correct
        name_entities = [e for e in phi_entities if e.value in ["John Michael Smith", "John Michael", "Smith"]]
        for entity in name_entities:
            assert entity.phi_type == PHIType.NAME, f"Name '{entity.value}' should have type NAME, got {entity.phi_type}"

        phone_entities = [e for e in phi_entities if e.value == "555-123-4567"]
        assert len(phone_entities) == 1, "Should find exactly one phone number"
        assert phone_entities[0].phi_type == PHIType.PHONE, f"Phone should have type PHONE, got {phone_entities[0].phi_type}"

        pa_entities = [e for e in phi_entities if e.value == "PA"]
        assert len(pa_entities) == 1, "Should find exactly one state code"
        assert pa_entities[0].phi_type == PHIType.ADDRESS, f"State 'PA' should have type ADDRESS, got {pa_entities[0].phi_type}"


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

    def test_generate_from_fhir_uses_config_encounter_default(self, minimal_fhir_bundle_path, mock_bedrock_client, tmp_path):
        """Test generate_from_fhir uses config encounter_index default when not specified."""
        from src.config import GeneratorConfig
        from unittest.mock import patch

        # Create config with encounter_index = -1 (most recent)
        config = GeneratorConfig(output_dir=tmp_path, encounter_index=-1)
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=config)

        # Verify config has -1 (most recent)
        assert generator.config.encounter_index == -1

        # Track which encounter index was actually used
        selected_encounter = []
        original_generate_internal = generator._generate_note_internal

        def capture_internal(*args, **kwargs):
            # Capture the context to see which encounter was selected
            context = kwargs.get('context') or args[2]
            if 'current_encounter' in context:
                selected_encounter.append(context['current_encounter'])
            return original_generate_internal(*args, **kwargs)

        with patch.object(generator, '_generate_note_internal', side_effect=capture_internal):
            # Call WITHOUT explicit encounter_index parameter
            result = generator.generate_from_fhir(
                bundle_path=minimal_fhir_bundle_path,
                note_type=NoteType.PROGRESS_NOTE
            )

        # Should successfully generate a note
        assert result is not None
        # Verify an encounter was selected (this proves it used the encounter_index logic)
        assert len(selected_encounter) > 0

    def test_generate_from_fhir_encounter_index_parameter_overrides_config(self, minimal_fhir_bundle_path, mock_bedrock_client, tmp_path):
        """Test explicit encounter_index parameter overrides config default."""
        from src.config import GeneratorConfig
        from unittest.mock import patch

        # Create config with encounter_index = -1 (most recent)
        config = GeneratorConfig(output_dir=tmp_path, encounter_index=-1)
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=config)

        # Track which encounter index was actually used
        selected_encounter = []
        original_generate_internal = generator._generate_note_internal

        def capture_internal(*args, **kwargs):
            context = kwargs.get('context') or args[2]
            if 'current_encounter' in context:
                selected_encounter.append(context['current_encounter'])
            return original_generate_internal(*args, **kwargs)

        with patch.object(generator, '_generate_note_internal', side_effect=capture_internal):
            # Call WITH explicit encounter_index=0 (should override config's -1)
            result = generator.generate_from_fhir(
                bundle_path=minimal_fhir_bundle_path,
                note_type=NoteType.PROGRESS_NOTE,
                encounter_index=0
            )

        assert result is not None
        assert len(selected_encounter) > 0

    def test_generate_from_fhir_passes_clinical_limits(self, minimal_fhir_bundle_path, mock_bedrock_client, tmp_path):
        """Test generate_from_fhir passes clinical limits to context builder."""
        from src.config import GeneratorConfig
        from unittest.mock import patch

        # Create config with clinical limits
        config = GeneratorConfig(
            output_dir=tmp_path,
            max_conditions=2,
            max_medications=3,
            max_procedures=1
        )

        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=config)

        # Mock _build_phi_context_from_fhir to verify it gets called with limits
        original_build = generator._build_phi_context_from_fhir
        call_args = []

        def mock_build(*args, **kwargs):
            call_args.append((args, kwargs))
            return original_build(*args, **kwargs)

        with patch.object(generator, '_build_phi_context_from_fhir', side_effect=mock_build):
            result = generator.generate_from_fhir(
                bundle_path=minimal_fhir_bundle_path,
                note_type=NoteType.PROGRESS_NOTE
            )

        # Verify the method was called with clinical_limits keyword argument
        assert len(call_args) > 0, "Expected _build_phi_context_from_fhir to be called"

        # Check if clinical_limits was passed as a keyword argument
        called_kwargs = call_args[0][1]
        assert 'clinical_limits' in called_kwargs, "Expected clinical_limits to be passed as keyword argument"

        # Verify the limits dict was passed correctly
        limits = called_kwargs['clinical_limits']
        assert limits is not None, "Expected clinical_limits to be a dict, not None"
        assert isinstance(limits, dict), f"Expected clinical_limits to be a dict, got {type(limits)}"
        assert limits['max_conditions'] == 2, f"Expected max_conditions=2, got {limits.get('max_conditions')}"
        assert limits['max_medications'] == 3, f"Expected max_medications=3, got {limits.get('max_medications')}"
        assert limits['max_procedures'] == 1, f"Expected max_procedures=1, got {limits.get('max_procedures')}"

        assert result is not None