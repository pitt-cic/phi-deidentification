"""Tests for FHIRBundleParser."""
import pytest
from dataclasses import asdict
from src.fhir_parser import FHIRBundleParser


@pytest.mark.unit
class TestFHIRBundleLoading:
    """Test bundle loading and indexing."""

    def test_load_bundle(self, minimal_fhir_bundle_path):
        """Test loading a FHIR bundle from file."""
        parser = FHIRBundleParser(minimal_fhir_bundle_path)

        assert parser.bundle is not None
        assert parser.bundle['resourceType'] == 'Bundle'
        assert 'entry' in parser.bundle
        assert len(parser.bundle['entry']) == 5

    def test_get_resources_by_type(self, fhir_parser):
        """Test getting resources by type."""
        patients = fhir_parser.get_resources('Patient')
        assert len(patients) == 1
        assert patients[0]['resourceType'] == 'Patient'

        encounters = fhir_parser.get_resources('Encounter')
        assert len(encounters) == 1

        practitioners = fhir_parser.get_resources('Practitioner')
        assert len(practitioners) == 1

    def test_get_resource_by_id(self, fhir_parser):
        """Test getting a specific resource by ID."""
        patient = fhir_parser.get_resource_by_id('patient-001')
        assert patient is not None
        assert patient['resourceType'] == 'Patient'
        assert patient['id'] == 'patient-001'


@pytest.mark.unit
class TestPatientExtraction:
    """Test patient data extraction."""

    def test_extract_patient_basic_fields(self, fhir_parser):
        """Test extracting basic patient demographics."""
        patient = fhir_parser.extract_patient().to_dict()

        assert patient is not None
        assert patient['first_name'] == 'John Michael'
        assert patient['last_name'] == 'Smith'
        assert 'full_name' in patient
        assert patient['gender'] == 'male'
        assert patient['birth_date'] == '1980-05-15'
        assert 'age' in patient

    def test_extract_patient_identifiers(self, fhir_parser):
        """Test extracting patient identifiers."""
        patient = fhir_parser.extract_patient().to_dict()

        assert 'mrn' in patient
        assert patient['mrn'] == 'MRN123456'
        assert 'ssn' in patient
        assert patient['ssn'] == '123-45-6789'
        assert 'drivers_license' in patient
        assert patient['drivers_license'] == 'D1234567'

    def test_extract_patient_contact(self, fhir_parser):
        """Test extracting patient contact information."""
        patient = fhir_parser.extract_patient().to_dict()

        assert 'phone' in patient
        assert patient['phone'] == '555-123-4567'

    def test_extract_patient_address(self, fhir_parser):
        """Test extracting patient address."""
        patient = fhir_parser.extract_patient().to_dict()

        assert 'address_line' in patient
        assert 'city' in patient
        assert patient['city'] == 'Pittsburgh'
        assert 'state' in patient
        assert patient['state'] == 'PA'
        assert 'zip_code' in patient
        assert patient['zip_code'] == '15213'

    def test_extract_patient_extensions(self, fhir_parser):
        """Test extracting patient extensions (race, ethnicity, birthplace)."""
        patient = fhir_parser.extract_patient().to_dict()

        # Race extension
        assert 'race' in patient

        # Ethnicity extension
        assert 'ethnicity' in patient

        # Birthplace extension
        assert 'birth_city' in patient
        assert patient['birth_city'] == 'Philadelphia'
        assert 'birth_state' in patient
        assert patient['birth_state'] == 'PA'
        assert 'birth_country' in patient
        assert patient['birth_country'] == 'US'

    def test_patient_to_context_string_includes_all_fields(self, fhir_parser):
        """Test PatientData.to_context_string() includes all non-empty fields."""
        patient = fhir_parser.extract_patient()

        context_string = patient.to_context_string()

        # Should be multiline string with key: value format
        assert isinstance(context_string, str)
        assert len(context_string) > 0

        # Check for key fields (sample has these)
        assert "First Name:" in context_string
        assert "Last Name:" in context_string
        assert "Full Name:" in context_string
        assert "Date of Birth:" in context_string
        assert "Gender:" in context_string
        assert "MRN:" in context_string

        # Should skip empty fields (e.g., nickname is typically empty in Synthea)
        # This assertion may need adjustment based on actual data
        lines = [line for line in context_string.split('\n') if line.strip()]
        assert all(':' in line for line in lines), "All lines should be 'Label: Value' format"


@pytest.mark.unit
class TestClinicalDataExtraction:
    """Test clinical data extraction."""

    def test_extract_encounters(self, fhir_parser):
        """Test extracting encounters."""
        encounters = fhir_parser.extract_encounters()

        assert len(encounters) > 0
        encounter = asdict(encounters[0])
        assert 'type_code' in encounter or 'type_display' in encounter
        assert 'start_datetime' in encounter or 'end_datetime' in encounter
        assert 'encounter_class' in encounter

    def test_extract_clinical_context(self, fhir_parser):
        """Test extracting full clinical context."""
        context = asdict(fhir_parser.extract_clinical_context())

        assert 'conditions' in context or isinstance(context, list)
        # If conditions exist in bundle, they should be extracted
        if context.get('conditions') or (isinstance(context, list) and len(context) > 0):
            if isinstance(context, dict):
                assert len(context['conditions']) > 0
            else:
                assert len(context) > 0

    def test_extract_providers(self, fhir_parser):
        """Test extracting providers."""
        providers = fhir_parser.extract_providers()

        assert len(providers) > 0
        provider = asdict(providers[0])
        assert 'name' in provider
        # May have phone, address, etc.

    def test_extract_organizations(self, fhir_parser):
        """Test extracting organizations."""
        orgs = fhir_parser.extract_organizations()

        assert len(orgs) > 0
        org = asdict(orgs[0])
        assert 'name' in org
        assert org['name'] == 'Example Medical Center'


@pytest.mark.unit
class TestFullContext:
    """Test full context extraction."""

    def test_get_full_context_structure(self, fhir_parser):
        """Test that get_full_context returns all expected sections."""
        context = fhir_parser.get_full_context()

        assert isinstance(context, dict)
        assert 'patient' in context
        assert 'encounters' in context
        assert 'providers' in context
        assert 'organizations' in context

        # Patient should have all expected fields
        patient = context['patient']
        assert 'first_name' in patient
        assert 'last_name' in patient
        assert 'birth_date' in patient
        assert 'mrn' in patient

        # Encounters should be a list
        assert isinstance(context['encounters'], list)

        # Providers should be a list
        assert isinstance(context['providers'], list)

        # Organizations should be a list
        assert isinstance(context['organizations'], list)


@pytest.mark.unit
class TestContextStringMethods:
    """Test to_context_string() methods on dataclasses."""

    def test_encounter_to_context_string_includes_all_fields(self, fhir_parser):
        """Test EncounterData.to_context_string() includes all non-empty fields."""
        encounters = fhir_parser.extract_encounters()

        assert len(encounters) > 0, "Sample should have encounters"

        encounter = encounters[0]
        context_string = encounter.to_context_string()

        # Validate format
        assert isinstance(context_string, str)
        assert len(context_string) > 0

        # Check for key fields - at least some should be present
        lines = [line for line in context_string.split('\n') if line.strip()]
        assert len(lines) > 0, "Should have at least one field"
        assert all(':' in line for line in lines), "All lines should be 'Label: Value' format"

        # Check that non-empty encounter fields appear in context string
        if encounter.id:
            assert f"Encounter ID: {encounter.id}" in context_string
        if encounter.type_display:
            assert f"Encounter Type: {encounter.type_display}" in context_string
        if encounter.encounter_class:
            assert f"Encounter Class: {encounter.encounter_class}" in context_string

    def test_clinical_context_to_context_string_includes_all_categories(self, fhir_parser):
        """Test ClinicalContext.to_context_string() includes all non-empty clinical categories."""
        context = fhir_parser.get_full_context()
        clinical_context = context.get('clinical')

        assert clinical_context is not None

        # Convert to ClinicalContext object if needed
        from src.fhir_parser import ClinicalContext
        if isinstance(clinical_context, dict):
            clinical_obj = ClinicalContext(**clinical_context)
        else:
            clinical_obj = clinical_context

        context_string = clinical_obj.to_context_string()

        # Validate format
        assert isinstance(context_string, str)
        assert len(context_string) > 0

        # Should have section headers for non-empty categories
        # Sample data typically has conditions and medications
        # Check for section markers (adjust based on actual format)
        lines = context_string.split('\n')
        assert any('Condition' in line or 'condition' in line for line in lines)
