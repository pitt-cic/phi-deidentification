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


class TestIsFinalFailureAttempt:
    """Tests for is_final_failure_attempt function."""

    def test_returns_false_when_not_final_attempt(self):
        """Should return False when receiveCount < maxReceiveCount."""
        # Attempt 1 of 3 - not final
        assert batch_stats.is_final_failure_attempt(receive_count=1, max_receive_count=3) is False
        # Attempt 2 of 3 - not final
        assert batch_stats.is_final_failure_attempt(receive_count=2, max_receive_count=3) is False

    def test_returns_true_on_final_attempt(self):
        """Should return True when receiveCount >= maxReceiveCount."""
        # Attempt 3 of 3 - final
        assert batch_stats.is_final_failure_attempt(receive_count=3, max_receive_count=3) is True
        # Beyond max (edge case) - still final
        assert batch_stats.is_final_failure_attempt(receive_count=4, max_receive_count=3) is True


class TestSetPartiallyCompletedStatus:
    """Tests for set_partially_completed_status function."""

    def test_sets_status_and_failed_at(self):
        """Test that set_partially_completed_status sets status and failed_at."""
        with patch.object(batch_stats, "STATS_TABLE_NAME", "test-table"), \
             patch.object(batch_stats, "boto3") as mock_boto3:
            batch_stats._stats_table = None
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            batch_stats.set_partially_completed_status("batch-001")

            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args.kwargs
            assert call_kwargs["Key"] == {"batch_id": "batch-001", "record_type": "BATCH"}
            assert "#status = :status" in call_kwargs["UpdateExpression"]
            assert "failed_at = if_not_exists(failed_at, :now)" in call_kwargs["UpdateExpression"]
            assert call_kwargs["ExpressionAttributeNames"]["#status"] == "status"
            assert call_kwargs["ExpressionAttributeValues"][":status"] == "partially-completed"

    def test_does_nothing_without_table(self):
        """Test that set_partially_completed_status does nothing when table not configured."""
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.set_partially_completed_status("batch-001")


class TestSetCompletedAtIfDoneWithStatus:
    """Tests for set_completed_at_if_done setting status."""

    def test_sets_status_completed_when_done(self):
        """Test that set_completed_at_if_done sets status to completed."""
        with patch.object(batch_stats, "STATS_TABLE_NAME", "test-table"), \
             patch.object(batch_stats, "boto3") as mock_boto3:
            batch_stats._stats_table = None
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            batch_stats.set_completed_at_if_done("batch-001")

            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args.kwargs
            assert call_kwargs["Key"] == {"batch_id": "batch-001", "record_type": "BATCH"}
            assert "#status = :status" in call_kwargs["UpdateExpression"]
            assert call_kwargs["ExpressionAttributeNames"]["#status"] == "status"
            assert call_kwargs["ExpressionAttributeValues"][":status"] == "completed"


class TestMarkNoteProcessed:
    """Tests for mark_note_processed function."""

    def test_marks_note_processed(self):
        """Test that mark_note_processed updates note with has_output=True."""
        with patch.object(batch_stats, "STATS_TABLE_NAME", "test-table"), \
             patch.object(batch_stats, "boto3") as mock_boto3:
            batch_stats._stats_table = None
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            batch_stats.mark_note_processed("batch-001", "note-123")

            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args.kwargs
            assert call_kwargs["Key"] == {"batch_id": "batch-001", "record_type": "NOTE#note-123"}
            assert call_kwargs["UpdateExpression"] == "SET has_output = :val"
            assert call_kwargs["ExpressionAttributeValues"][":val"] is True

    def test_does_nothing_without_table(self):
        """Test that mark_note_processed does nothing when table not configured."""
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.mark_note_processed("batch-001", "note-123")

    def test_logs_warning_on_error(self):
        """Test that mark_note_processed logs warning on DynamoDB error."""
        with patch.object(batch_stats, "STATS_TABLE_NAME", "test-table"), \
             patch.object(batch_stats, "boto3") as mock_boto3:
            batch_stats._stats_table = None
            mock_table = MagicMock()
            mock_table.update_item.side_effect = Exception("DynamoDB error")
            mock_boto3.resource.return_value.Table.return_value = mock_table

            mock_logger = MagicMock()
            batch_stats.mark_note_processed("batch-001", "note-123", logger=mock_logger)

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0]
            assert "note-123" in call_args[1]
