"""Tests for FHIRBundleParser."""
import pytest
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
