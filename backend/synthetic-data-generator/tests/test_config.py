"""Tests for configuration module."""

import pytest
from synthetic_data_generator.config import AWSConfig, DEFAULT_AWS_CONFIG, GeneratorConfig


class TestAWSConfig:
    """Test AWSConfig dataclass."""

    def test_default_retry_timeout_settings(self):
        """Test AWSConfig has retry/timeout defaults."""
        config = AWSConfig()
        assert config.read_timeout == 120
        assert config.connect_timeout == 10
        assert config.max_retries == 4
        assert config.retry_mode == "adaptive"

    def test_custom_retry_timeout_settings(self):
        """Test AWSConfig accepts custom retry/timeout values."""
        config = AWSConfig(
            read_timeout=300,
            connect_timeout=30,
            max_retries=5,
            retry_mode="standard"
        )
        assert config.read_timeout == 300
        assert config.connect_timeout == 30
        assert config.max_retries == 5
        assert config.retry_mode == "standard"


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
    assert config.max_conditions == 5  # Default limit for efficiency
    assert config.max_observations == 10  # Slightly higher for observations
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
