"""Tests for configuration module."""

import pytest
from src.config import GeneratorConfig


def test_generator_config_has_clinical_limit_fields():
    """Test GeneratorConfig has clinical limit configuration fields."""
    config = GeneratorConfig()

    # Verify new fields exist
    assert hasattr(config, 'max_conditions')
    assert hasattr(config, 'max_medications')
    assert hasattr(config, 'max_procedures')
    assert hasattr(config, 'max_allergies')
    assert hasattr(config, 'max_immunizations')
    assert hasattr(config, 'max_observations')
    assert hasattr(config, 'max_imaging_studies')
    assert hasattr(config, 'max_devices')
    assert hasattr(config, 'encounter_index')

    # Verify defaults
    assert config.max_conditions is None  # None = unlimited
    assert config.encounter_index == -1  # Most recent by default


def test_generator_config_clinical_limits_configurable():
    """Test clinical limits can be configured."""
    config = GeneratorConfig(
        max_conditions=5,
        max_medications=10,
        encounter_index=0
    )

    assert config.max_conditions == 5
    assert config.max_medications == 10
    assert config.encounter_index == 0
