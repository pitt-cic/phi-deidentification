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
