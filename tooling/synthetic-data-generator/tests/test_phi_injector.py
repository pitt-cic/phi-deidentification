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

