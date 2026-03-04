"""Tests for agent models."""

import pytest

from agent.models import (
    CompactAgentResponse,
    AgentResponse,
    PIIEntity,
    expand_compact_response,
    SHORT_TO_FULL_TYPE,
)


class TestExpandCompactResponse:
    """Tests for expand_compact_response function."""

    def test_empty_response_returns_empty_entities(self):
        compact = CompactAgentResponse()
        result = expand_compact_response(compact)
        assert isinstance(result, AgentResponse)
        assert result.pii_entities == []

    def test_single_type_single_value(self):
        compact = CompactAgentResponse(nam=["John"])
        result = expand_compact_response(compact)
        assert len(result.pii_entities) == 1
        assert result.pii_entities[0].type == "person_name"
        assert result.pii_entities[0].value == "John"

    def test_single_type_multiple_values(self):
        compact = CompactAgentResponse(nam=["John", "Jane", "Dr. Smith"])
        result = expand_compact_response(compact)
        assert len(result.pii_entities) == 3
        assert all(e.type == "person_name" for e in result.pii_entities)
        assert [e.value for e in result.pii_entities] == ["John", "Jane", "Dr. Smith"]

    def test_multiple_types(self):
        compact = CompactAgentResponse(
            nam=["John"],
            adr=["123 Main St"],
            mrn=["MRN-12345"],
        )
        result = expand_compact_response(compact)
        assert len(result.pii_entities) == 3

        types = {e.type for e in result.pii_entities}
        assert types == {"person_name", "address", "medical_record_number"}

        values = {e.value for e in result.pii_entities}
        assert values == {"John", "123 Main St", "MRN-12345"}

    def test_all_types_covered(self):
        """Verify all short codes map to valid full types."""
        # Build a compact response with one value per type
        kwargs = {short: [f"test_{short}"] for short in SHORT_TO_FULL_TYPE.keys()}
        compact = CompactAgentResponse(**kwargs)
        result = expand_compact_response(compact)

        assert len(result.pii_entities) == len(SHORT_TO_FULL_TYPE)
        result_types = {e.type for e in result.pii_entities}
        assert result_types == set(SHORT_TO_FULL_TYPE.values())
