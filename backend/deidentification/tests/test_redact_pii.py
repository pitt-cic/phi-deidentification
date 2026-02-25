"""Tests for redact_pii module."""

import pytest

from deidentification.redaction.redact_pii import redact_text, RedactionResult
from deidentification.redaction.redaction_formats import RedactionFormat, RedactionFormatter


class TestRedactTextBasic:
    """Basic redaction functionality tests."""

    def test_empty_entities_returns_original_text(self):
        text = "Hello world"
        result = redact_text(text, [])
        assert result.text == "Hello world"
        assert result.skipped_by_type == {}

    def test_empty_text_returns_empty(self):
        entities = [{"type": "person_name", "value": "John"}]
        result = redact_text("", entities)
        assert result.text == ""
        assert result.skipped_by_type == {}

    def test_single_replacement(self):
        text = "Hi John, how are you?"
        entities = [{"type": "person_name", "value": "John"}]
        result = redact_text(text, entities)
        assert result.text == "Hi [PERSON_NAME], how are you?"
        assert result.skipped_by_type == {}

    def test_multiple_occurrences_same_value(self):
        text = "John met John at the park"
        entities = [{"type": "person_name", "value": "John"}]
        result = redact_text(text, entities)
        assert result.text == "[PERSON_NAME] met [PERSON_NAME] at the park"
        assert result.skipped_by_type == {}


class TestRedactTextGrouping:
    """Tests for group-by-type behavior."""

    def test_multiple_entities_same_type(self):
        text = "John met Jane at the cafe"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "person_name", "value": "Jane"},
        ]
        result = redact_text(text, entities)
        assert result.text == "[PERSON_NAME] met [PERSON_NAME] at the cafe"
        assert result.skipped_by_type == {}

    def test_longest_first_within_type(self):
        """Longer values should be replaced before shorter to avoid partial matches."""
        text = "John Smith called John yesterday"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "person_name", "value": "John Smith"},
        ]
        result = redact_text(text, entities)
        # "John Smith" replaced first, standalone "John" also replaced
        assert result.text == "[PERSON_NAME] called [PERSON_NAME] yesterday"
        assert result.skipped_by_type == {}

    def test_mixed_types(self):
        text = "John's email is john@example.com"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "email", "value": "john@example.com"},
        ]
        result = redact_text(text, entities)
        assert "[PERSON_NAME]" in result.text
        assert "[EMAIL]" in result.text
        assert result.skipped_by_type == {}

    def test_same_value_different_types(self):
        """Same value in different types - first replacement wins."""
        text = "Contact John for details"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "other", "value": "John"},
        ]
        result = redact_text(text, entities)
        # One of the types will replace it, the other silently skipped
        assert "John" not in result.text
        assert result.skipped_by_type == {}


class TestRedactTextSkipTracking:
    """Tests for skip tracking behavior."""

    def test_all_skipped_in_type_tracked(self):
        """When ALL entities of a type are not found, track it."""
        text = "Hello world"
        entities = [{"type": "person_name", "value": "John"}]
        result = redact_text(text, entities)
        assert result.text == "Hello world"
        assert result.skipped_by_type == {"person_name": 1}

    def test_partial_skip_silent(self):
        """When SOME entities of a type match, don't track skips."""
        text = "Hi John"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "person_name", "value": "Jane"},  # not in text
        ]
        result = redact_text(text, entities)
        assert result.text == "Hi [PERSON_NAME]"
        # Jane not found, but John was - so no skip tracked
        assert result.skipped_by_type == {}

    def test_substring_consumed_silent(self):
        """When shorter value consumed by longer, don't track as skip."""
        text = "John Smith is here"
        entities = [
            {"type": "person_name", "value": "John Smith"},
            {"type": "person_name", "value": "John"},  # consumed by John Smith
        ]
        result = redact_text(text, entities)
        assert result.text == "[PERSON_NAME] is here"
        # "John" not found separately, but "John Smith" matched - no skip
        assert result.skipped_by_type == {}

    def test_mixed_types_one_fully_skipped(self):
        """Mixed types where one type is fully skipped."""
        text = "Hi John"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "email", "value": "test@example.com"},  # not in text
        ]
        result = redact_text(text, entities)
        assert result.text == "Hi [PERSON_NAME]"
        assert result.skipped_by_type == {"email": 1}

    def test_multiple_skipped_same_type(self):
        """Multiple entities of same type all skipped."""
        text = "Hello world"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "person_name", "value": "Jane"},
        ]
        result = redact_text(text, entities)
        assert result.text == "Hello world"
        assert result.skipped_by_type == {"person_name": 2}

    def test_all_types_fully_skipped(self):
        """All types fully skipped."""
        text = "Hello world"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "email", "value": "test@example.com"},
        ]
        result = redact_text(text, entities)
        assert result.text == "Hello world"
        assert result.skipped_by_type == {"person_name": 1, "email": 1}


class TestRedactTextFormatter:
    """Tests for custom formatter integration."""

    def test_custom_formatter_used(self):
        """Verify custom formatter produces expected tags."""
        text = "John called Jane"
        entities = [
            {"type": "person_name", "value": "John"},
            {"type": "person_name", "value": "Jane"},
        ]
        fmt = RedactionFormat(template="**{TYPE}[{ID}]", id_scheme="alpha")
        formatter = RedactionFormatter(fmt)

        result = redact_text(text, entities, formatter=formatter)

        assert "**NAME[A]" in result.text
        assert "**NAME[B]" in result.text
        assert result.skipped_by_type == {}


class TestRedactTextTypeOrdering:
    """Tests for deterministic PII type ordering."""

    def test_type_order_prevents_substring_corruption(self):
        """Ensure longer values in specific types are not corrupted by shorter values in generic types."""
        text = "Patient insurance: AETNA-681277021 Provider: AETNA"
        entities = [
            {"type": "other", "value": "AETNA"},
            {"type": "health_plan_beneficiary_number", "value": "AETNA-681277021"},
        ]
        result = redact_text(text, entities)
        # health_plan_beneficiary_number (index 8) should process before other (index 17)
        assert "[HEALTH_PLAN_BENEFICIARY_NUMBER]" in result.text
        assert "AETNA-681277021" not in result.text
        # "AETNA" alone should also be replaced (appears separately as "Provider: AETNA")
        assert "[OTHER]" in result.text
        assert result.text == "Patient insurance: [HEALTH_PLAN_BENEFICIARY_NUMBER] Provider: [OTHER]"

    def test_unknown_type_processed_after_other(self):
        """Unknown types should be processed after 'other'."""
        text = "Custom: SECRET123 Other: INFO"
        entities = [
            {"type": "custom_field", "value": "SECRET123"},  # unknown type
            {"type": "other", "value": "INFO"},
        ]
        result = redact_text(text, entities)
        # Both should be replaced
        assert "SECRET123" not in result.text
        assert "INFO" not in result.text
        assert "[CUSTOM_FIELD]" in result.text
        assert "[OTHER]" in result.text
