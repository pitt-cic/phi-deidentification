"""Shared test fixtures for PHI Note Generator tests."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.config import GeneratorConfig, NoteType
from src.fhir_parser import FHIRBundleParser
from src.phi_generator import PHIGenerator
from src.phi_injector import PHIInjector
from src.note_generator import NoteGenerator
from src.bedrock_client import BedrockClient


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_fhir_bundle_path(fixtures_dir):
    """Return path to minimal FHIR bundle fixture."""
    return fixtures_dir / "minimal_fhir_bundle.json"


@pytest.fixture
def minimal_fhir_bundle(minimal_fhir_bundle_path):
    """Load minimal FHIR bundle JSON."""
    with open(minimal_fhir_bundle_path) as f:
        return json.load(f)


@pytest.fixture
def mock_bedrock_client():
    """Mock BedrockClient that returns predefined text."""
    mock = Mock(spec=BedrockClient)
    mock.generate.return_value = """EMERGENCY DEPARTMENT NOTE

Patient: John Doe
DOB: 1980-05-15
MRN: 12345-67890

Chief Complaint: Patient presents with chest pain.

History: The patient is a 43-year-old male with history of hypertension.

Contact: Phone 555-123-4567, Email john.doe@example.com"""
    return mock


@pytest.fixture
def mock_phi_generator():
    """Mock PHIGenerator with deterministic output."""
    mock = Mock(spec=PHIGenerator)
    mock.generate_email.return_value = "test@example.com"
    mock.generate_email_domain.return_value = "example.com"
    mock.generate_fax.return_value = "555-0199"
    mock.generate_health_plan_id.return_value = "HP-12345"
    mock.generate_account_number.return_value = "ACC-98765"
    mock.generate_vehicle_id.return_value = "VIN-ABC123"
    mock.generate_license_plate.return_value = "ABC-1234"
    mock.generate_ip_address.return_value = "192.168.1.100"
    mock.generate_patient_portal_url.return_value = "https://portal.example.com"
    mock.generate_phone.return_value = "555-1234"
    mock.generate_hospital_name.return_value = "General Hospital"
    mock.generate_provider_name.return_value = "Dr. Smith"
    mock.generate_device_id.return_value = "DEV-12345"
    mock.generate_name.return_value = {"first_name": "John", "last_name": "Doe", "full_name": "John Doe"}
    mock.generate_ssn.return_value = "999-99-9999"
    mock.generate_mrn.return_value = "MRN-123456"
    mock.generate_address.return_value = "123 Main St, Boston, MA 02101"
    mock.generate_dob.return_value = ("1980-01-15", "%Y-%m-%d")
    mock_fake = Mock()
    mock_fake.random_int.return_value = 12345
    mock.fake = mock_fake
    return mock


@pytest.fixture
def test_config(tmp_path):
    """Test configuration with temporary output directory."""
    return GeneratorConfig(output_dir=tmp_path)


@pytest.fixture
def fhir_parser(minimal_fhir_bundle_path):
    """FHIRBundleParser instance with minimal bundle loaded."""
    parser = FHIRBundleParser(minimal_fhir_bundle_path)
    return parser
