"""Tests for API batch_stats module."""

import base64
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load the batch_stats module directly since 'lambda' is a Python reserved keyword
_module_path = Path(__file__).parent.parent / "batch_stats.py"
_spec = importlib.util.spec_from_file_location("api_batch_stats", _module_path)
batch_stats = importlib.util.module_from_spec(_spec)
sys.modules["api_batch_stats"] = batch_stats
_spec.loader.exec_module(batch_stats)


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    batch_stats._dynamodb_resource = None
    batch_stats._stats_table = None
    yield


class TestGetBatchStats:
    """Tests for get_batch_stats function."""

    def test_returns_none_when_table_not_configured(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        result = batch_stats.get_batch_stats("test-batch")

        assert result is None

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_none_when_item_not_found(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert result is None

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_stats_when_found(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "test-batch",
                "input_count": Decimal("100"),
                "processed_count": Decimal("100"),
                "approved_count": Decimal("50"),
                "total_entities": Decimal("500"),
                "notes_with_pii": Decimal("80"),
                "pii_person_name": Decimal("200"),
                "pii_address": Decimal("100"),
                "pii_date": Decimal("0"),
                "status": "completed",  # Status is read from DB
                "created_at": "2026-02-21T10:00:00Z",
                "started_at": "2026-02-21T10:00:00Z",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert result["batch_id"] == "test-batch"
        assert result["status"] == "completed"  # Status read directly from DB
        assert result["input_count"] == 100
        assert result["output_count"] == 100
        assert "failed_count" not in result  # No longer included in response

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_filters_zero_pii_counts(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "test-batch",
                "input_count": Decimal("100"),
                "processed_count": Decimal("100"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("300"),
                "notes_with_pii": Decimal("80"),
                "pii_person_name": Decimal("200"),
                "pii_address": Decimal("100"),
                "pii_date": Decimal("0"),  # Should be filtered out
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert "PERSON_NAME" in result["pii_stats"]["by_type"]
        assert "ADDRESS" in result["pii_stats"]["by_type"]
        assert "DATE" not in result["pii_stats"]["by_type"]

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_sorts_pii_by_count_descending(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "test-batch",
                "input_count": Decimal("100"),
                "processed_count": Decimal("100"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("300"),
                "notes_with_pii": Decimal("80"),
                "pii_address": Decimal("100"),
                "pii_person_name": Decimal("200"),
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        by_type = result["pii_stats"]["by_type"]
        keys = list(by_type.keys())
        assert keys[0] == "PERSON_NAME"  # 200, comes first
        assert keys[1] == "ADDRESS"  # 100, comes second

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_reads_status_from_db(self, mock_boto3):
        """Test that status is read directly from DB, not computed."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "test-batch",
                "input_count": Decimal("100"),
                "processed_count": Decimal("50"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("0"),
                "notes_with_pii": Decimal("0"),
                "status": "processing",  # Status is stored in DB
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert result["status"] == "processing"  # Read from DB, not computed

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_computes_all_approved(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "test-batch",
                "input_count": Decimal("100"),
                "processed_count": Decimal("100"),
                "approved_count": Decimal("100"),  # All approved
                "total_entities": Decimal("0"),
                "notes_with_pii": Decimal("0"),
                "status": "completed",  # Status is read from DB
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert result["all_approved"] is True


class TestIncrementApprovalCount:
    """Tests for increment_approval_count function."""

    def test_does_nothing_when_table_not_configured(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.increment_approval_count("test-batch", 1)

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_increments_approval_count(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.increment_approval_count("test-batch", 1)

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":delta"] == 1

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_decrements_approval_count(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.increment_approval_count("test-batch", -1)

        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":delta"] == -1


class TestGetBatchStatsPartiallyCompleted:
    """Tests for status being read from DB (not computed)."""

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_partially_completed_from_db(self, mock_boto3):
        """Test status is read directly from DB as partially-completed."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("7"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("50"),
                "notes_with_pii": Decimal("5"),
                "status": "partially-completed",  # Status stored in DB
                "created_at": "2026-02-26T10:00:00+00:00",
                "started_at": "2026-02-26T10:00:05+00:00",
                "failed_at": "2026-02-26T10:02:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result is not None
        assert result["status"] == "partially-completed"
        assert "failed_count" not in result  # No longer included in response
        assert result["failed_at"] == "2026-02-26T10:02:00+00:00"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_completed_from_db(self, mock_boto3):
        """Test status is read directly from DB as completed."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("10"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("50"),
                "notes_with_pii": Decimal("5"),
                "status": "completed",  # Status stored in DB
                "created_at": "2026-02-26T10:00:00+00:00",
                "started_at": "2026-02-26T10:00:05+00:00",
                "completed_at": "2026-02-26T10:05:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result is not None
        assert result["status"] == "completed"
        assert "failed_count" not in result  # No longer included in response

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_processing_from_db(self, mock_boto3):
        """Test status is read directly from DB as processing."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("5"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("30"),
                "notes_with_pii": Decimal("3"),
                "status": "processing",  # Status stored in DB
                "created_at": "2026-02-26T10:00:00+00:00",
                "started_at": "2026-02-26T10:00:05+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result is not None
        assert result["status"] == "processing"


class TestGetBatchStatsReadsStatusDirectly:
    """Tests for get_batch_stats reading status from DynamoDB directly."""

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_status_from_db_without_computation(self, mock_boto3):
        """Test that status is read directly from DynamoDB, not computed."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("10"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("50"),
                "notes_with_pii": Decimal("5"),
                "status": "completed",  # Status stored in DB
                "created_at": "2026-03-01T10:00:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result["status"] == "completed"
        # Importantly: no failed_count in response
        assert "failed_count" not in result

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_partially_completed_from_db(self, mock_boto3):
        """Test that partially-completed status is preserved from DB."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("7"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("30"),
                "notes_with_pii": Decimal("3"),
                "status": "partially-completed",  # Status stored in DB
                "failed_at": "2026-03-01T10:02:00+00:00",
                "created_at": "2026-03-01T10:00:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result["status"] == "partially-completed"
        assert result["failed_at"] == "2026-03-01T10:02:00+00:00"


class TestSetProcessingStatusForRedrive:
    """Tests for set_processing_status_for_redrive function."""

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_sets_processing_status_and_redrive_timestamp(self, mock_boto3):
        """Test that function sets status=processing and last_redrive_at."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.set_processing_status_for_redrive("batch-001")

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["Key"] == {"batch_id": "batch-001", "record_type": "BATCH"}
        assert "last_redrive_at = :now" in call_kwargs["UpdateExpression"]
        assert "#status = :status" in call_kwargs["UpdateExpression"]
        assert call_kwargs["ExpressionAttributeNames"]["#status"] == "status"
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "processing"
        # No failed_count reset
        assert "failed_count" not in call_kwargs["UpdateExpression"]

    def test_does_nothing_when_table_not_configured(self):
        """Test that function does nothing when table not configured."""
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.set_processing_status_for_redrive("batch-001")


class TestListAllBatches:
    """Tests for list_all_batches function."""

    def test_returns_empty_when_table_not_configured(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        result = batch_stats.list_all_batches(limit=50, cursor=None)

        assert result == {"items": [], "next_cursor": None}

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_queries_gsi_with_correct_params(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.list_all_batches(limit=50, cursor=None)

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args.kwargs
        assert call_kwargs["IndexName"] == "BatchesByCreatedAt"
        assert call_kwargs["ScanIndexForward"] is False
        assert call_kwargs["Limit"] == 50

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_items_from_query(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {"batch_id": "batch-001", "status": "completed"},
                {"batch_id": "batch-002", "status": "processing"},
            ]
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.list_all_batches(limit=50, cursor=None)

        assert len(result["items"]) == 2
        assert result["next_cursor"] is None

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_next_cursor_when_more_items(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [{"batch_id": "batch-001"}],
            "LastEvaluatedKey": {"batch_id": "batch-001", "record_type": "BATCH"},
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.list_all_batches(limit=50, cursor=None)

        assert result["next_cursor"] is not None


class TestIsRecentlyUpdated:
    """Tests for _is_recently_updated helper function."""

    def test_returns_true_when_within_threshold(self):
        """Should return True when timestamp is within threshold minutes."""
        # 1 minute ago is within 2-minute threshold
        one_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        result = batch_stats._is_recently_updated(one_min_ago, threshold_minutes=2)

        assert result is True

    def test_returns_false_when_beyond_threshold(self):
        """Should return False when timestamp is beyond threshold minutes."""
        # 5 minutes ago is beyond 2-minute threshold
        five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        result = batch_stats._is_recently_updated(five_min_ago, threshold_minutes=2)

        assert result is False

    def test_returns_false_for_empty_string(self):
        """Should return False for empty timestamp."""
        result = batch_stats._is_recently_updated("", threshold_minutes=2)

        assert result is False

    def test_returns_false_for_invalid_timestamp(self):
        """Should return False for invalid timestamp format."""
        result = batch_stats._is_recently_updated("not-a-timestamp", threshold_minutes=2)

        assert result is False


class TestGetBatchStatsStatusOverride:
    """Tests for status override when partially-completed but still processing."""

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_processing_when_partially_completed_but_recently_updated(self, mock_boto3):
        """Should return 'processing' when status is partially-completed but updated_at is recent."""
        batch_stats._stats_table = None

        # updated_at is 1 minute ago (recent)
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("100"),
                "processed_count": Decimal("50"),  # Not all processed
                "approved_count": Decimal("0"),
                "total_entities": Decimal("200"),
                "notes_with_pii": Decimal("30"),
                "status": "partially-completed",  # DB has partially-completed
                "failed_at": "2026-03-03T10:00:00+00:00",
                "updated_at": recent_time,  # But recently updated
                "created_at": "2026-03-03T09:00:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        # Should override to 'processing' because still active
        assert result["status"] == "processing"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_partially_completed_when_not_recently_updated(self, mock_boto3):
        """Should return 'partially-completed' when updated_at is stale."""
        batch_stats._stats_table = None

        # updated_at is 5 minutes ago (stale)
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("100"),
                "processed_count": Decimal("50"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("200"),
                "notes_with_pii": Decimal("30"),
                "status": "partially-completed",
                "failed_at": "2026-03-03T10:00:00+00:00",
                "updated_at": stale_time,  # Not recently updated
                "created_at": "2026-03-03T09:00:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        # Should return actual status because processing stopped
        assert result["status"] == "partially-completed"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_partially_completed_when_all_processed(self, mock_boto3):
        """Should return 'partially-completed' when processed_count >= input_count."""
        batch_stats._stats_table = None

        # Even if recently updated, if all notes processed, show actual status
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("100"),
                "processed_count": Decimal("100"),  # All processed
                "approved_count": Decimal("0"),
                "total_entities": Decimal("400"),
                "notes_with_pii": Decimal("80"),
                "status": "partially-completed",  # But some failed
                "failed_at": "2026-03-03T10:00:00+00:00",
                "updated_at": recent_time,
                "created_at": "2026-03-03T09:00:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        # Should NOT override because all notes have been attempted
        assert result["status"] == "partially-completed"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_does_not_override_other_statuses(self, mock_boto3):
        """Should not override completed or processing statuses."""
        batch_stats._stats_table = None

        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("100"),
                "processed_count": Decimal("100"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("400"),
                "notes_with_pii": Decimal("80"),
                "status": "completed",  # Not partially-completed
                "updated_at": recent_time,
                "created_at": "2026-03-03T09:00:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result["status"] == "completed"


class TestListNotesFromDynamo:
    """Tests for list_notes_from_dynamo function."""

    def test_returns_empty_when_table_not_configured(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        result = batch_stats.list_notes_from_dynamo("test-batch", limit=50, cursor=None)

        assert result == {"items": [], "next_cursor": None}

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_queries_notes_with_correct_params(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.list_notes_from_dynamo("batch-001", limit=50, cursor=None)

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args.kwargs
        assert call_kwargs["Limit"] == 50
        assert "ExclusiveStartKey" not in call_kwargs

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_items_from_query(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "batch_id": "batch-001",
                    "record_type": "NOTE#note-1",
                    "note_id": "note-1",
                    "has_output": True,
                    "approved": False,
                },
                {
                    "batch_id": "batch-001",
                    "record_type": "NOTE#note-2",
                    "note_id": "note-2",
                    "has_output": True,
                    "approved": True,
                },
            ]
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.list_notes_from_dynamo("batch-001", limit=50, cursor=None)

        assert len(result["items"]) == 2
        assert result["items"][0]["note_id"] == "note-1"
        assert result["items"][0]["has_output"] is True
        assert result["items"][0]["approved"] is False
        assert result["items"][1]["note_id"] == "note-2"
        assert result["items"][1]["approved"] is True
        assert result["next_cursor"] is None

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_next_cursor_when_more_items(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [{"batch_id": "batch-001", "record_type": "NOTE#note-1", "note_id": "note-1"}],
            "LastEvaluatedKey": {"batch_id": "batch-001", "record_type": "NOTE#note-1"},
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.list_notes_from_dynamo("batch-001", limit=50, cursor=None)

        assert result["next_cursor"] is not None

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_handles_cursor_pagination(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Create a valid cursor
        cursor = base64.b64encode(
            json.dumps({"batch_id": "batch-001", "record_type": "NOTE#note-1"}).encode()
        ).decode()

        batch_stats.list_notes_from_dynamo("batch-001", limit=50, cursor=cursor)

        call_kwargs = mock_table.query.call_args.kwargs
        assert "ExclusiveStartKey" in call_kwargs
        assert call_kwargs["ExclusiveStartKey"]["batch_id"] == "batch-001"
        assert call_kwargs["ExclusiveStartKey"]["record_type"] == "NOTE#note-1"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_handles_invalid_cursor_gracefully(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Invalid cursor should be ignored
        batch_stats.list_notes_from_dynamo("batch-001", limit=50, cursor="invalid-cursor")

        call_kwargs = mock_table.query.call_args.kwargs
        assert "ExclusiveStartKey" not in call_kwargs

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_extracts_note_id_from_record_type_when_missing(self, mock_boto3):
        """Test fallback when note_id attribute is missing."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "batch_id": "batch-001",
                    "record_type": "NOTE#note-1",
                    # note_id attribute missing
                    "has_output": True,
                    "approved": False,
                },
            ]
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.list_notes_from_dynamo("batch-001", limit=50, cursor=None)

        assert len(result["items"]) == 1
        assert result["items"][0]["note_id"] == "note-1"  # Extracted from record_type


class TestUpdateNoteApprovedStatus:
    """Tests for update_note_approved_status function."""

    def test_does_nothing_when_table_not_configured(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.update_note_approved_status("test-batch", "note-1", True)

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_updates_note_approved_to_true(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.update_note_approved_status("batch-001", "note-1", True)

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["Key"] == {"batch_id": "batch-001", "record_type": "NOTE#note-1"}
        assert call_kwargs["UpdateExpression"] == "SET approved = :val"
        assert call_kwargs["ExpressionAttributeValues"][":val"] is True

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_updates_note_approved_to_false(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.update_note_approved_status("batch-001", "note-1", False)

        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["ExpressionAttributeValues"][":val"] is False
