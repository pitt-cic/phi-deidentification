"""Async AWS Bedrock client wrapper for Claude API calls."""

import json
from typing import Optional

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import AWSConfig, DEFAULT_AWS_CONFIG


class AsyncBedrockClient:
    """Async client for interacting with AWS Bedrock Claude models."""

    def __init__(self, config: Optional[AWSConfig] = None):
        self.config = config or DEFAULT_AWS_CONFIG
        self._session = aioboto3.Session()
        self._boto_config = Config(
            read_timeout=self.config.read_timeout,
            connect_timeout=self.config.connect_timeout,
            retries={
                "total_max_attempts": self.config.max_retries,
                "mode": self.config.retry_mode
            }
        )

    async def generate(
        self,
        prompt: str,
        system_role: str = "You are a helpful assistant.",
    ) -> str:
        """
        Generate text using Claude on Bedrock asynchronously.

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
            async with self._session.client(
                "bedrock-runtime",
                region_name=self.config.region,
                config=self._boto_config
            ) as client:
                response = await client.invoke_model(
                    modelId=self.config.model_id,
                    body=json.dumps(request_body)
                )

                response_body = await response["body"].read()
                model_response = json.loads(response_body)
                usage = model_response.get("usage", {})
                print(f"Tokens: input={usage.get('input_tokens', 0)}, output={usage.get('output_tokens', 0)}")
                return model_response["content"][0]["text"]

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            print(f"Bedrock API error: {error_code}", e)
            raise RuntimeError(f"Bedrock API error: {error_code}") from e
