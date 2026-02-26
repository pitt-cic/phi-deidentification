"""Tests for worker batch_stats module."""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load the batch_stats module directly since 'lambda' is a Python reserved keyword
_module_path = Path(__file__).parent.parent / "batch_stats.py"
_spec = importlib.util.spec_from_file_location("worker_batch_stats", _module_path)
batch_stats = importlib.util.module_from_spec(_spec)
sys.modules["worker_batch_stats"] = batch_stats
_spec.loader.exec_module(batch_stats)


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    batch_stats._dynamodb_resource = None
    batch_stats._stats_table = None
    yield


class TestPiiTypeToAttribute:
    """Tests for pii_type_to_attribute function."""

    def test_converts_uppercase_to_lowercase(self):
        assert batch_stats.pii_type_to_attribute("PERSON_NAME") == "pii_person_name"

    def test_handles_mixed_case(self):
        assert batch_stats.pii_type_to_attribute("Person_Name") == "pii_person_name"

    def test_replaces_spaces_with_underscores(self):
        assert batch_stats.pii_type_to_attribute("PERSON NAME") == "pii_person_name"


class TestIncrementBatchStats:
    """Tests for increment_batch_stats function."""

    def test_does_nothing_when_table_name_not_set(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.increment_batch_stats("test-batch", [{"type": "PERSON_NAME", "value": "John"}])

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_increments_processed_count(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.increment_batch_stats("test-batch", [])

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert "processed_count :one" in call_kwargs["UpdateExpression"]
        assert call_kwargs["ExpressionAttributeValues"][":one"] == 1

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_increments_entity_counts(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        entities = [
            {"type": "PERSON_NAME", "value": "John"},
            {"type": "PERSON_NAME", "value": "Jane"},
            {"type": "ADDRESS", "value": "123 Main St"},
        ]
        batch_stats.increment_batch_stats("test-batch", entities)

        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":entities"] == 3
        assert call_kwargs["ExpressionAttributeValues"][":has_pii"] == 1

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_groups_pii_by_type(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        entities = [
            {"type": "PERSON_NAME", "value": "John"},
            {"type": "PERSON_NAME", "value": "Jane"},
        ]
        batch_stats.increment_batch_stats("test-batch", entities)

        call_kwargs = mock_table.update_item.call_args[1]
        update_expr = call_kwargs["UpdateExpression"]
        assert "pii_person_name" in update_expr

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_handles_unknown_type(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        entities = [{"value": "something"}]  # No type
        batch_stats.increment_batch_stats("test-batch", entities)

        call_kwargs = mock_table.update_item.call_args[1]
        update_expr = call_kwargs["UpdateExpression"]
        assert "pii_unknown" in update_expr

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_logs_warning_on_error(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DynamoDB error")
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_logger = MagicMock()

        # Should not raise, should log
        batch_stats.increment_batch_stats("test-batch", [], logger=mock_logger)

        mock_logger.warning.assert_called_once()


class TestIncrementFailedCount:
    """Tests for increment_failed_count function."""

    def test_increment_failed_count_increments_and_sets_failed_at(self):
        """Test that increment_failed_count increments failed_count and sets failed_at."""
        with patch.object(batch_stats, "STATS_TABLE_NAME", "test-table"), \
             patch.object(batch_stats, "boto3") as mock_boto3:
            batch_stats._stats_table = None
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            batch_stats.increment_failed_count("batch-001")

            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args.kwargs
            assert call_kwargs["Key"] == {"batch_id": "batch-001"}
            assert "failed_count" in call_kwargs["UpdateExpression"]
            assert "failed_at" in call_kwargs["UpdateExpression"]
            assert ":one" in call_kwargs["ExpressionAttributeValues"]
            assert call_kwargs["ExpressionAttributeValues"][":one"] == 1

    def test_increment_failed_count_does_nothing_without_table(self):
        """Test that increment_failed_count does nothing when table not configured."""
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.increment_failed_count("batch-001")
