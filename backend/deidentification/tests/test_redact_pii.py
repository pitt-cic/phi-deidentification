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
    pass


class TestRedactTextSkipTracking:
    """Tests for skip tracking behavior."""
    pass
