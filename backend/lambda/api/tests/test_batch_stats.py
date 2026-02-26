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
                "status": "processing",
                "created_at": "2026-02-21T10:00:00Z",
                "started_at": "2026-02-21T10:00:00Z",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert result["batch_id"] == "test-batch"
        assert result["status"] == "completed"  # processed >= input
        assert result["input_count"] == 100
        assert result["output_count"] == 100

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
    def test_computes_status_processing(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "test-batch",
                "input_count": Decimal("100"),
                "processed_count": Decimal("50"),  # < input
                "approved_count": Decimal("0"),
                "total_entities": Decimal("0"),
                "notes_with_pii": Decimal("0"),
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("test-batch")

        assert result["status"] == "processing"

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
    """Tests for partially-completed status computation."""

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_partially_completed_when_failures_exist(self, mock_boto3):
        """Test status is partially-completed when processed + failed >= input and failed > 0."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("7"),
                "failed_count": Decimal("3"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("50"),
                "notes_with_pii": Decimal("5"),
                "created_at": "2026-02-26T10:00:00+00:00",
                "started_at": "2026-02-26T10:00:05+00:00",
                "failed_at": "2026-02-26T10:02:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result is not None
        assert result["status"] == "partially-completed"
        assert result["failed_count"] == 3
        assert result["failed_at"] == "2026-02-26T10:02:00+00:00"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_completed_when_no_failures(self, mock_boto3):
        """Test status is completed when all notes processed successfully."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("10"),
                "failed_count": Decimal("0"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("50"),
                "notes_with_pii": Decimal("5"),
                "created_at": "2026-02-26T10:00:00+00:00",
                "started_at": "2026-02-26T10:00:05+00:00",
                "completed_at": "2026-02-26T10:05:00+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result is not None
        assert result["status"] == "completed"
        assert result["failed_count"] == 0

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_returns_processing_when_in_progress(self, mock_boto3):
        """Test status is processing when not all notes handled yet."""
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "batch_id": "batch-001",
                "input_count": Decimal("10"),
                "processed_count": Decimal("5"),
                "failed_count": Decimal("1"),
                "approved_count": Decimal("0"),
                "total_entities": Decimal("30"),
                "notes_with_pii": Decimal("3"),
                "created_at": "2026-02-26T10:00:00+00:00",
                "started_at": "2026-02-26T10:00:05+00:00",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        result = batch_stats.get_batch_stats("batch-001")

        assert result is not None
        assert result["status"] == "processing"
