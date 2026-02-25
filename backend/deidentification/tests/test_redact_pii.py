"""Tests for redact_pii module."""

import pytest

from deidentification.redaction.redact_pii import redact_text, RedactionResult


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
    pass
