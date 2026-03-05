"""Tests for BedrockClient."""

import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from synthetic_data_generator.bedrock_client import BedrockClient
from synthetic_data_generator.config import AWSConfig


@pytest.fixture
def aws_config():
    """Test AWS config."""
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
def mock_boto3_client():
    """Mock boto3 client."""
    mock_response = {
        "body": MagicMock()
    }
    mock_response["body"].read.return_value = b'{"content": [{"text": "Generated response"}]}'

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = mock_response
    return mock_client


@pytest.mark.unit
class TestBedrockClient:
    """Test BedrockClient functionality."""

    def test_init_with_default_config(self):
        """Test client initializes with default config."""
        client = BedrockClient()
        assert client.config is not None
        assert client.config.region == "us-east-1"

    def test_init_with_custom_config(self, aws_config):
        """Test client initializes with custom config."""
        client = BedrockClient(config=aws_config)
        assert client.config == aws_config

    def test_client_creates_boto_config(self, aws_config):
        """Test client creates botocore Config from AWSConfig."""
        client = BedrockClient(config=aws_config)
        assert client._boto_config is not None
        assert client._boto_config.read_timeout == 120
        assert client._boto_config.connect_timeout == 10

    def test_generate_returns_text(self, aws_config, mock_boto3_client):
        """Test generate() returns text from Bedrock response."""
        with patch("boto3.client", return_value=mock_boto3_client):
            client = BedrockClient(config=aws_config)
            result = client.generate(
                prompt="Test prompt",
                system_role="You are helpful."
            )
        assert result == "Generated response"

    def test_generate_raises_on_client_error(self, aws_config):
        """Test generate() raises RuntimeError on ClientError."""
        mock_client = MagicMock()
        error_response = {"Error": {"Code": "ValidationException", "Message": "Invalid"}}
        mock_client.invoke_model.side_effect = ClientError(error_response, "invoke_model")

        with patch("boto3.client", return_value=mock_client):
            client = BedrockClient(config=aws_config)
            with pytest.raises(RuntimeError, match="Bedrock API error"):
                client.generate(prompt="Test")
