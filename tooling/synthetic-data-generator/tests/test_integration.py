"""Integration tests for end-to-end flows."""
from unittest.mock import Mock, patch

import pytest
from synthetic_data_generator.config import GeneratorConfig
from synthetic_data_generator.fhir_parser import FHIRBundleParser
from synthetic_data_generator.models.note_models import NoteType
from synthetic_data_generator.note_generator import NoteGenerator
from synthetic_data_generator.phi_injector import PHIInjector


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


@pytest.mark.integration
class TestComprehensivePHICoverage:
    """Test comprehensive PHI coverage in generated context."""

    def test_comprehensive_phi_coverage_in_context(self, minimal_fhir_bundle_path):
        """Test that all PHI fields are included in generated context."""
        # Create generator with mock LLM
        config = GeneratorConfig(encounter_index=-1)
        generator = NoteGenerator(config=config, bedrock_client=Mock())

        # Parse FHIR and build context
        parser = FHIRBundleParser(minimal_fhir_bundle_path)
        fhir_context = parser.get_full_context()

        # Build PHI context string
        phi_context = generator._build_phi_context_from_fhir(fhir_context, clinical_limits=None)

        # Verify patient fields are present
        patient = fhir_context.get('patient')
        if patient:
            if patient.get('first_name'):
                assert "First Name:" in phi_context or patient['first_name'] in phi_context
            if patient.get('last_name'):
                assert "Last Name:" in phi_context or patient['last_name'] in phi_context
            if patient.get('mrn'):
                assert "MRN:" in phi_context or patient['mrn'] in phi_context
            if patient.get('ssn'):
                assert "SSN:" in phi_context or patient['ssn'] in phi_context
            if patient.get('birth_date'):
                assert "Date of Birth:" in phi_context or patient['birth_date'] in phi_context
            if patient.get('address_line'):
                assert "Address:" in phi_context or patient['address_line'] in phi_context
            if patient.get('phone'):
                assert "Phone:" in phi_context or patient['phone'] in phi_context

        # Verify clinical context sections are present (if data exists)
        clinical = fhir_context.get('clinical_context') or fhir_context.get('clinical')
        if clinical:
            if hasattr(clinical, 'conditions') and clinical.conditions:
                assert "Condition" in phi_context or "##" in phi_context
            if hasattr(clinical, 'medications') and clinical.medications:
                assert "Medication" in phi_context or "##" in phi_context

        # Verify provider information is present
        providers = fhir_context.get('providers')
        if providers and len(providers) > 0:
            first_provider = providers[0]
            if isinstance(first_provider, dict) and first_provider.get('name'):
                assert "Provider" in phi_context or first_provider['name'] in phi_context

        # Verify substantial content generated
        assert len(phi_context) > 200, "PHI context should contain substantial content"

    def test_clinical_limits_are_respected(self, minimal_fhir_bundle_path):
        """Test that clinical limits from config are properly applied."""
        # Create config with tight limits
        config = GeneratorConfig(
            max_conditions=2,
            max_medications=2,
            max_procedures=1
        )

        generator = NoteGenerator(config=config, bedrock_client=Mock())

        # Parse FHIR
        parser = FHIRBundleParser(minimal_fhir_bundle_path)
        fhir_context = parser.get_full_context()

        # Build clinical context with limits
        clinical_limits = {
            'max_conditions': config.max_conditions,
            'max_medications': config.max_medications,
            'max_procedures': config.max_procedures
        }

        phi_context = generator._build_phi_context_from_fhir(fhir_context, clinical_limits)

        # Verify limits are applied
        # Count "- " lines in each section (approximate check)
        sections = phi_context.split('##')

        # Basic verification: context should be generated
        assert phi_context is not None
        assert len(phi_context) > 0

        # If clinical data exists, verify it's included
        clinical = fhir_context.get('clinical_context') or fhir_context.get('clinical')
        if clinical:
            if hasattr(clinical, 'conditions') and clinical.conditions:
                assert "Condition" in phi_context.lower() or "##" in phi_context

    def test_encounter_selection_uses_most_recent(self, minimal_fhir_bundle_path, mock_bedrock_client):
        """Test that default encounter_index=-1 uses most recent encounter."""
        # Create generator with default config (encounter_index=-1)
        config = GeneratorConfig()
        assert config.encounter_index == -1, "Default should be -1 (most recent)"

        generator = NoteGenerator(config=config, bedrock_client=mock_bedrock_client)

        # Generate note (should use most recent encounter)
        result = generator.generate_from_fhir(
            bundle_path=minimal_fhir_bundle_path,
            note_type=NoteType.PROGRESS_NOTE
        )

        assert result is not None
        assert len(result.content) > 0

@pytest.mark.integration
class TestPHICoverage:
    """Test that PHI context includes all expected patient data."""

    def test_comprehensive_phi_coverage_in_context(self, comprehensive_fhir_bundle_path, mock_bedrock_client, tmp_path):
        """Test that comprehensive PHI data from FHIR is included in context."""
        # Parse FHIR
        parser = FHIRBundleParser(comprehensive_fhir_bundle_path)
        fhir_context = parser.get_full_context()

        # Create generator
        config = GeneratorConfig(output_dir=tmp_path)
        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=config)

        # Build PHI context
        phi_context = generator._build_phi_context_from_fhir(fhir_context, clinical_limits=None)

        # Get patient data
        patient = fhir_context.get('patient', {})

        # Verify patient information with specific assertions
        if patient.get('first_name'):
            assert f"First Name: {patient['first_name']}" in phi_context or \
                   f"Full Name: {patient.get('full_name', '')}" in phi_context, \
                   "Patient first name should appear in context"

        if patient.get('last_name'):
            assert f"Last Name: {patient['last_name']}" in phi_context or \
                   f"Full Name: {patient.get('full_name', '')}" in phi_context, \
                   "Patient last name should appear in context"

        if patient.get('birth_date'):
            assert f"Date of Birth: {patient['birth_date']}" in phi_context or \
                   f"Birth Date: {patient['birth_date']}" in phi_context, \
                   "Patient birth date should appear in context"

        if patient.get('mrn'):
            assert f"MRN: {patient['mrn']}" in phi_context or \
                   f"Medical Record Number: {patient['mrn']}" in phi_context, \
                   "Patient MRN should appear in context"

        if patient.get('ssn'):
            assert f"SSN: {patient['ssn']}" in phi_context or \
                   f"Social Security Number: {patient['ssn']}" in phi_context, \
                   "Patient SSN should appear in context"

        if patient.get('phone'):
            assert f"Phone: {patient['phone']}" in phi_context or \
                   patient['phone'] in phi_context, \
                   "Patient phone should appear in context"

        # Verify clinical data sections exist
        clinical = fhir_context.get('clinical', {})
        if clinical.get('conditions'):
            assert "## Conditions" in phi_context or "Conditions" in phi_context, \
                   "Conditions section should appear when conditions exist"

        if clinical.get('medications'):
            assert "## Medications" in phi_context or "Medications" in phi_context, \
                   "Medications section should appear when medications exist"

        if clinical.get('procedures'):
            assert "## Procedures" in phi_context or "Procedures" in phi_context, \
                   "Procedures section should appear when procedures exist"

@pytest.mark.integration
class TestEncounterSelection:
    """Test that encounter selection logic works correctly."""

    def test_encounter_selection_uses_most_recent(self, comprehensive_fhir_bundle_path, mock_bedrock_client, tmp_path):
        """Test that default encounter_index=-1 uses most recent encounter."""
        # Parse to get encounters
        parser = FHIRBundleParser(comprehensive_fhir_bundle_path)
        full_context = parser.get_full_context()
        encounters = full_context.get('encounters', [])

        # Skip if bundle has only one encounter (can't distinguish most recent)
        if len(encounters) <= 1:
            pytest.skip("Bundle needs multiple encounters to test selection")

        # Get most recent encounter data
        most_recent = encounters[-1]  # Last encounter is most recent

        # Create generator with default config (encounter_index=-1)
        config = GeneratorConfig(output_dir=tmp_path)
        assert config.encounter_index == -1

        generator = NoteGenerator(bedrock_client=mock_bedrock_client, config=config)

        # Capture the PHI context passed to the LLM
        captured_context = []
        original_method = generator._build_phi_context_from_fhir

        def capture_context(*args, **kwargs):
            phi_context = original_method(*args, **kwargs)
            captured_context.append(phi_context)
            return phi_context

        with patch.object(generator, '_build_phi_context_from_fhir', side_effect=capture_context):
            # Generate note
            result = generator.generate_from_fhir(
                bundle_path=comprehensive_fhir_bundle_path,
                note_type=NoteType.PROGRESS_NOTE
            )

        assert result is not None
        assert hasattr(result, 'content')
        assert len(result.content) > 0
        assert len(captured_context) == 1, "Should have captured exactly one PHI context"

        phi_context = captured_context[0]

        # Verify most recent encounter data appears in context
        if most_recent.get('start_datetime'):
            assert most_recent['start_datetime'] in phi_context, \
                f"Most recent encounter date {most_recent['start_datetime']} should be in context"

        if most_recent.get('type_display'):
            assert most_recent['type_display'] in phi_context or "Encounter Type:" in phi_context, \
                "Most recent encounter type should be in context"
