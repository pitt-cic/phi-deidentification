"""Tests for PHIInjector."""
import pytest
from synthetic_data_generator.phi_injector import PHIInjector


@pytest.mark.unit
class TestPHIInjector:
    """Test PHI injection logic."""

    def test_inject_basic_phi(self, fhir_parser, mock_phi_generator):
        """Test that inject adds expected PHI fields."""
        synthea_context = fhir_parser.get_full_context()
        injector = PHIInjector(phi_generator=mock_phi_generator)

        enhanced = injector.inject(synthea_context)

        # Should have injected section
        assert 'injected' in enhanced
        assert 'email' in enhanced['injected']
        assert 'fax' in enhanced['injected']
        assert 'health_plan_id' in enhanced['injected']
        assert 'device_id' in enhanced['injected']

    def test_inject_creates_facility(self, fhir_parser, mock_phi_generator):
        """Test that facility info is created."""
        synthea_context = fhir_parser.get_full_context()
        injector = PHIInjector(phi_generator=mock_phi_generator)

        enhanced = injector.inject(synthea_context)

        assert 'facility' in enhanced
        assert 'name' in enhanced['facility']
        assert 'phone' in enhanced['facility']
        assert 'fax' in enhanced['facility']

    def test_inject_creates_providers_if_missing(self, mock_phi_generator):
        """Test that providers are created if missing from context."""
        empty_context = {'patient': {}, 'encounters': [], 'organizations': []}
        injector = PHIInjector(phi_generator=mock_phi_generator)

        enhanced = injector.inject(empty_context)

        assert 'providers' in enhanced
        assert len(enhanced['providers']) > 0
        assert 'name' in enhanced['providers'][0]
        assert 'email' in enhanced['providers'][0]
        assert 'fax' in enhanced['providers'][0]

    def test_inject_email_construction(self, fhir_parser, mock_phi_generator):
        """Test email is constructed from patient name."""
        synthea_context = fhir_parser.get_full_context()
        injector = PHIInjector(phi_generator=mock_phi_generator)

        enhanced = injector.inject(synthea_context)

        # Email should be flattened into patient dict
        assert 'email' in enhanced['patient']
        # Should contain patient name components
        email = enhanced['patient']['email']
        assert '@' in email

    def test_inject_device_ids(self, fhir_parser, mock_phi_generator):
        """Test device IDs are added."""
        synthea_context = fhir_parser.get_full_context()
        injector = PHIInjector(phi_generator=mock_phi_generator)

        enhanced = injector.inject(synthea_context)

        assert 'device' in enhanced
        assert 'id' in enhanced['device']
        assert 'scanner_id' in enhanced['device']