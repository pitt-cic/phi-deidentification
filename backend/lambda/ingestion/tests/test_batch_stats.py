"""Tests for batch_stats module."""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load the batch_stats module directly since 'lambda' is a Python reserved keyword
_module_path = Path(__file__).parent.parent / "batch_stats.py"
_spec = importlib.util.spec_from_file_location("batch_stats", _module_path)
batch_stats = importlib.util.module_from_spec(_spec)
sys.modules["batch_stats"] = batch_stats
_spec.loader.exec_module(batch_stats)


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    batch_stats._dynamodb_resource = None
    batch_stats._stats_table = None
    yield


class TestBuildInitialStatsItem:
    """Tests for build_initial_stats_item function."""

    def test_creates_item_with_correct_batch_id(self):
        item = batch_stats.build_initial_stats_item("test-batch", 100)

        assert item["batch_id"] == "test-batch"

    def test_creates_item_with_correct_input_count(self):
        item = batch_stats.build_initial_stats_item("test-batch", 100)

        assert item["input_count"] == 100

    def test_initializes_counters_to_zero(self):
        item = batch_stats.build_initial_stats_item("test-batch", 100)

        assert item["processed_count"] == 0
        assert item["total_entities"] == 0
        assert item["notes_with_pii"] == 0
        assert item["approved_count"] == 0

    def test_initializes_all_pii_type_counts_to_zero(self):
        item = batch_stats.build_initial_stats_item("test-batch", 100)

        pii_types = [
            "pii_person_name", "pii_address", "pii_date", "pii_other",
            "pii_phone_number", "pii_certificate_or_license_number",
            "pii_vehicle_identifier", "pii_medical_record_number",
            "pii_health_plan_beneficiary_number", "pii_account_number",
            "pii_email", "pii_ssn", "pii_fax_number", "pii_device_identifier",
            "pii_ip_address", "pii_biometric_identifier", "pii_unknown",
        ]
        for pii_type in pii_types:
            assert item[pii_type] == 0, f"{pii_type} should be 0"

    def test_sets_status_to_processing(self):
        item = batch_stats.build_initial_stats_item("test-batch", 100)

        assert item["status"] == "processing"

    def test_sets_timestamps(self):
        item = batch_stats.build_initial_stats_item("test-batch", 100)

        assert "created_at" in item
        assert "started_at" in item
        assert "updated_at" in item
        assert item["created_at"] == item["started_at"]


class TestInitializeBatchStats:
    """Tests for initialize_batch_stats function."""

    @patch.dict(os.environ, {"STATS_TABLE_NAME": ""})
    def test_does_nothing_when_table_name_not_set(self):
        # Reload module to pick up env var change
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.initialize_batch_stats("test-batch", 100)

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_creates_new_item_when_not_exists(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.initialize_batch_stats("test-batch", 100)

        mock_table.put_item.assert_called_once()
        call_kwargs = mock_table.put_item.call_args[1]
        assert call_kwargs["Item"]["batch_id"] == "test-batch"
        assert call_kwargs["Item"]["record_type"] == "BATCH"
        assert call_kwargs["ConditionExpression"] == "attribute_not_exists(batch_id) AND attribute_not_exists(record_type)"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_updates_when_exists(self, mock_boto3):
        """When item exists, update status to processing instead of delete+recreate."""
        from botocore.exceptions import ClientError

        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # put_item raises ConditionalCheckFailedException (item exists)
        error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        mock_table.put_item.side_effect = ClientError(error_response, "PutItem")

        batch_stats.initialize_batch_stats("test-batch", 100)

        # Should NOT delete
        mock_table.delete_item.assert_not_called()
        # Should update instead
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"] == {"batch_id": "test-batch", "record_type": "BATCH"}
        assert ":status" in call_kwargs["ExpressionAttributeValues"]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "processing"
        assert call_kwargs["ExpressionAttributeValues"][":input_count"] == 100


def test_build_initial_stats_item_includes_record_type():
    """Test that record_type is included for GSI."""
    item = batch_stats.build_initial_stats_item("batch-001", 10)
    assert item["record_type"] == "BATCH"


def test_build_initial_stats_item_includes_record_type():
    """Test that record_type is included for composite key."""
    item = batch_stats.build_initial_stats_item("batch-001", 10)
    assert item["record_type"] == "BATCH"


class TestBuildInitialStatsItemNoFailedCount:
    """Tests for build_initial_stats_item without failed_count."""

    def test_build_initial_stats_item_does_not_include_failed_count(self):
        """Test that initial stats do NOT include failed_count."""
        item = batch_stats.build_initial_stats_item("batch-001", 10)

        assert "failed_count" not in item
        assert "completed_at" not in item  # Should not be set initially
        assert "failed_at" not in item  # Should not be set initially


class TestWriteNoteMetadata:
    """Tests for write_note_metadata function."""

    @patch.dict(os.environ, {"STATS_TABLE_NAME": ""})
    def test_does_nothing_when_table_name_not_set(self):
        batch_stats.STATS_TABLE_NAME = ""
        batch_stats._stats_table = None

        # Should not raise
        batch_stats.write_note_metadata("test-batch", "note-001")

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_writes_note_metadata_item(self, mock_boto3):
        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        batch_stats.write_note_metadata("test-batch", "note-001")

        mock_table.put_item.assert_called_once()
        call_kwargs = mock_table.put_item.call_args[1]
        assert call_kwargs["Item"]["batch_id"] == "test-batch"
        assert call_kwargs["Item"]["record_type"] == "NOTE#note-001"
        assert call_kwargs["Item"]["note_id"] == "note-001"
        assert call_kwargs["Item"]["has_output"] is False
        assert call_kwargs["Item"]["approved"] is False
        assert call_kwargs["ConditionExpression"] == "attribute_not_exists(batch_id) AND attribute_not_exists(record_type)"

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_ignores_conditional_check_failed_exception(self, mock_boto3):
        """Note already exists, should be ignored gracefully."""
        from botocore.exceptions import ClientError

        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # put_item raises ConditionalCheckFailedException (note already exists)
        error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        mock_table.put_item.side_effect = ClientError(error_response, "PutItem")

        # Should not raise
        batch_stats.write_note_metadata("test-batch", "note-001")

    @patch.object(batch_stats, "STATS_TABLE_NAME", "test-table")
    @patch.object(batch_stats, "boto3")
    def test_raises_on_other_exceptions(self, mock_boto3):
        """Non-ConditionalCheckFailedException errors should be raised."""
        from botocore.exceptions import ClientError

        batch_stats._stats_table = None

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # put_item raises some other error
        error_response = {"Error": {"Code": "SomeOtherError"}}
        mock_table.put_item.side_effect = ClientError(error_response, "PutItem")

        # Should raise
        with pytest.raises(ClientError):
            batch_stats.write_note_metadata("test-batch", "note-001")
