"""AWS Bedrock client wrapper for Claude API calls."""

import json
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import AWSConfig, DEFAULT_AWS_CONFIG


class BedrockClient:
    """Client for interacting with AWS Bedrock Claude models."""

    def __init__(self, config: Optional[AWSConfig] = None):
        self.config = config or DEFAULT_AWS_CONFIG
        self._boto_config = Config(
            read_timeout=self.config.read_timeout,
            connect_timeout=self.config.connect_timeout,
            retries={
                "total_max_attempts": self.config.max_retries,
                "mode": self.config.retry_mode
            }
        )
        self._client = None

    @property
    def client(self):
        """Lazy initialization of boto3 client."""
        if self._client is None:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.config.region,
                config=self._boto_config
            )
        return self._client

    def generate(
        self,
        prompt: str,
        system_role: str = "You are a helpful assistant.",
    ) -> str:
        """
        Generate text using Claude on Bedrock.

        Args:
            prompt: The user prompt to send
            system_role: System message defining Claude's role

        Returns:
            Generated text response

        Raises:
            RuntimeError: If generation fails
        """
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "system": system_role,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ]
        }

        try:
            response = self.client.invoke_model(
                modelId=self.config.model_id,
                body=json.dumps(request_body)
            )

            model_response = json.loads(response["body"].read())
            return model_response["content"][0]["text"]

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            raise RuntimeError(f"Bedrock API error: {error_code}") from e
