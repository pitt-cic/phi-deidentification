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


def test_generator_config_rejects_invalid_encounter_index():
    """Test GeneratorConfig rejects invalid encounter_index values."""
    # Valid values should work
    GeneratorConfig(encounter_index=-1)  # Most recent
    GeneratorConfig(encounter_index=0)   # Oldest
    GeneratorConfig(encounter_index=5)   # Specific index

    # Invalid values should raise ValueError
    with pytest.raises(ValueError, match="encounter_index must be -1 or >= 0"):
        GeneratorConfig(encounter_index=-2)

    with pytest.raises(ValueError, match="encounter_index must be -1 or >= 0"):
        GeneratorConfig(encounter_index=-100)


def test_generator_config_rejects_negative_clinical_limits():
    """Test GeneratorConfig rejects negative max_* values."""
    # Valid values should work
    GeneratorConfig(max_conditions=None)  # Unlimited
    GeneratorConfig(max_conditions=0)     # Zero is valid (skip category)
    GeneratorConfig(max_conditions=10)    # Positive

    # Negative values should raise ValueError
    with pytest.raises(ValueError, match="max_conditions must be None or non-negative"):
        GeneratorConfig(max_conditions=-1)

    with pytest.raises(ValueError, match="max_medications must be None or non-negative"):
        GeneratorConfig(max_medications=-5)
