"""Tests for AsyncNoteGenerator."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synthetic_data_generator.async_note_generator import AsyncNoteGenerator
from synthetic_data_generator.config import GeneratorConfig
from synthetic_data_generator.models.note_models import GeneratedNote, NoteType


@pytest.fixture
def async_config(tmp_path):
    """Test configuration for async generator."""
    config = GeneratorConfig(output_dir=tmp_path)
    config.ensure_dirs()
    return config


@pytest.fixture
def mock_async_bedrock():
    """Mock AsyncBedrockClient."""
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value="""EMERGENCY DEPARTMENT NOTE

Patient: John Smith
DOB: 1980-05-15
MRN: 12345

Chief Complaint: Chest pain.""")
    return mock


@pytest.mark.asyncio
@pytest.mark.unit
class TestAsyncNoteGeneratorInit:
    """Test AsyncNoteGenerator initialization."""

    async def test_init_with_default_rate_limit(self, async_config):
        """Test generator initializes with default 150 RPM rate limit."""
        generator = AsyncNoteGenerator(config=async_config)
        assert generator.rate_limit == 150

    async def test_init_with_custom_rate_limit(self, async_config):
        """Test generator initializes with custom rate limit."""
        generator = AsyncNoteGenerator(config=async_config, rate_limit=100)
        assert generator.rate_limit == 100


@pytest.mark.asyncio
@pytest.mark.unit
class TestAsyncNoteGeneratorGeneration:
    """Test note generation functionality."""

    async def test_generate_note_returns_generated_note(
        self, async_config, mock_async_bedrock, minimal_fhir_bundle_path
    ):
        """Test generate_note returns a GeneratedNote object."""
        with patch(
            "synthetic_data_generator.async_note_generator.AsyncBedrockClient",
            return_value=mock_async_bedrock
        ):
            generator = AsyncNoteGenerator(config=async_config)
            generator.bedrock = mock_async_bedrock

            result = await generator.generate_note(
                bundle_path=minimal_fhir_bundle_path,
                note_type=NoteType.EMERGENCY_DEPT
            )

        assert isinstance(result, GeneratedNote)
        assert result.note_type == NoteType.EMERGENCY_DEPT
        assert result.content is not None

    async def test_generate_note_respects_rate_limit(
        self, async_config, mock_async_bedrock, minimal_fhir_bundle_path
    ):
        """Test that generate_note acquires rate limiter before calling Bedrock."""
        with patch(
            "synthetic_data_generator.async_note_generator.AsyncBedrockClient",
            return_value=mock_async_bedrock
        ):
            generator = AsyncNoteGenerator(config=async_config, rate_limit=150)
            generator.bedrock = mock_async_bedrock

            # Track limiter acquisition
            limiter_acquired = False
            original_acquire = generator.limiter.acquire

            async def track_acquire(*args, **kwargs):
                nonlocal limiter_acquired
                limiter_acquired = True
                return await original_acquire(*args, **kwargs)

            generator.limiter.acquire = track_acquire

            await generator.generate_note(
                bundle_path=minimal_fhir_bundle_path,
                note_type=NoteType.EMERGENCY_DEPT
            )

        assert limiter_acquired, "Rate limiter should be acquired before generation"


@pytest.mark.asyncio
@pytest.mark.unit
class TestAsyncNoteGeneratorBulk:
    """Test bulk generation functionality."""

    async def test_generate_all_processes_all_tasks(
        self, async_config, mock_async_bedrock, minimal_fhir_bundle_path
    ):
        """Test generate_all processes all tasks and returns results."""
        with patch(
            "synthetic_data_generator.async_note_generator.AsyncBedrockClient",
            return_value=mock_async_bedrock
        ):
            generator = AsyncNoteGenerator(config=async_config)
            generator.bedrock = mock_async_bedrock

            tasks = [
                (minimal_fhir_bundle_path, NoteType.EMERGENCY_DEPT),
                (minimal_fhir_bundle_path, NoteType.DISCHARGE_SUMMARY),
                (minimal_fhir_bundle_path, NoteType.PROGRESS_NOTE),
            ]

            notes, errors = await generator.generate_all(tasks)

        assert len(notes) == 3
        assert len(errors) == 0
        assert all(isinstance(n, GeneratedNote) for n in notes)

    async def test_generate_all_collects_errors(
        self, async_config, minimal_fhir_bundle_path
    ):
        """Test generate_all collects errors without stopping."""
        mock_bedrock = AsyncMock()
        call_count = 0

        async def generate_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated failure")
            return """EMERGENCY DEPARTMENT NOTE
Patient: John Smith
DOB: 1980-05-15"""

        mock_bedrock.generate = generate_with_error

        with patch(
            "synthetic_data_generator.async_note_generator.AsyncBedrockClient",
            return_value=mock_bedrock
        ):
            generator = AsyncNoteGenerator(config=async_config)
            generator.bedrock = mock_bedrock

            tasks = [
                (minimal_fhir_bundle_path, NoteType.EMERGENCY_DEPT),
                (minimal_fhir_bundle_path, NoteType.DISCHARGE_SUMMARY),
                (minimal_fhir_bundle_path, NoteType.PROGRESS_NOTE),
            ]

            notes, errors = await generator.generate_all(tasks)

        assert len(notes) == 2
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)

    async def test_generate_all_saves_notes(
        self, async_config, mock_async_bedrock, minimal_fhir_bundle_path
    ):
        """Test generate_all saves notes to disk."""
        with patch(
            "synthetic_data_generator.async_note_generator.AsyncBedrockClient",
            return_value=mock_async_bedrock
        ):
            generator = AsyncNoteGenerator(config=async_config)
            generator.bedrock = mock_async_bedrock

            tasks = [(minimal_fhir_bundle_path, NoteType.EMERGENCY_DEPT)]

            notes, errors = await generator.generate_all(tasks)

        assert len(notes) == 1
        # Verify file was saved
        saved_files = list(async_config.notes_dir.glob("*.txt"))
        assert len(saved_files) == 1
