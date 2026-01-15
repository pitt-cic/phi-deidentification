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
