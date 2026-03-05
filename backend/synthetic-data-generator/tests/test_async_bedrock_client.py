"""Tests for AsyncBedrockClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from botocore.exceptions import ClientError

from synthetic_data_generator.async_bedrock_client import AsyncBedrockClient
from synthetic_data_generator.config import AWSConfig


@pytest.fixture
def aws_config():
    """Test AWS config with retry/timeout settings."""
    return AWSConfig(
        region="us-east-1",
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        max_tokens=4000,
        temperature=0.7,
        read_timeout=120,
        connect_timeout=10,
        max_retries=4,
        retry_mode="adaptive"
    )


@pytest.fixture
def mock_aioboto3_session():
    """Mock aioboto3 session with async context manager."""
    mock_response = {
        "body": MagicMock()
    }
    mock_response["body"].read = AsyncMock(return_value=b'{"content": [{"text": "Generated response"}]}')

    mock_client = AsyncMock()
    mock_client.invoke_model = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_client)

    return mock_session


@pytest.mark.asyncio
@pytest.mark.unit
class TestAsyncBedrockClient:
    """Test AsyncBedrockClient functionality."""

    async def test_init_with_default_config(self):
        """Test client initializes with default config."""
        client = AsyncBedrockClient()
        assert client.config is not None
        assert client.config.region == "us-east-1"

    async def test_init_with_custom_config(self, aws_config):
        """Test client initializes with custom config."""
        client = AsyncBedrockClient(config=aws_config)
        assert client.config == aws_config

    async def test_generate_returns_text(self, aws_config, mock_aioboto3_session):
        """Test generate() returns text from Bedrock response."""
        with patch("synthetic_data_generator.async_bedrock_client.aioboto3.Session", return_value=mock_aioboto3_session):
            client = AsyncBedrockClient(config=aws_config)
            result = await client.generate(
                prompt="Test prompt",
                system_role="You are a helpful assistant."
            )

        assert result == "Generated response"

    async def test_generate_raises_on_client_error(self, aws_config):
        """Test generate() raises RuntimeError on ClientError."""
        async def mock_invoke(*args, **kwargs):
            error_response = {"Error": {"Code": "ValidationException", "Message": "Invalid input"}}
            raise ClientError(error_response, "invoke_model")

        mock_client = AsyncMock()
        mock_client.invoke_model = mock_invoke
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_client)

        with patch("synthetic_data_generator.async_bedrock_client.aioboto3.Session", return_value=mock_session):
            client = AsyncBedrockClient(config=aws_config)
            with pytest.raises(RuntimeError, match="Bedrock API error"):
                await client.generate(prompt="Test")


@pytest.mark.asyncio
@pytest.mark.unit
class TestAsyncBedrockClientBotocoreConfig:
    """Test botocore Config integration."""

    async def test_client_creates_boto_config(self, aws_config):
        """Test client creates botocore Config from AWSConfig."""
        client = AsyncBedrockClient(config=aws_config)
        assert client._boto_config is not None
        assert client._boto_config.read_timeout == 120
        assert client._boto_config.connect_timeout == 10

    async def test_generate_simplified_signature(self, aws_config, mock_aioboto3_session):
        """Test generate() no longer accepts retry params."""
        with patch("synthetic_data_generator.async_bedrock_client.aioboto3.Session", return_value=mock_aioboto3_session):
            client = AsyncBedrockClient(config=aws_config)
            result = await client.generate(
                prompt="Test prompt",
                system_role="You are helpful."
            )
        assert result == "Generated response"
