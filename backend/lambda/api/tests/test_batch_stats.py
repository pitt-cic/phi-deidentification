"""Tests for API batch_stats module."""

import importlib.util
import os
import sys
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
        assert call_kwargs["Key"] == {"batch_id": "batch-001"}
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
            "LastEvaluatedKey": {"batch_id": "batch-001", "gsi_pk": "BATCH"},
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.list_all_batches(limit=50, cursor=None)

        assert result["next_cursor"] is not None
