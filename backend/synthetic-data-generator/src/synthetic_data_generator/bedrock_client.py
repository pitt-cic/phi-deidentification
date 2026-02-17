"""AWS Bedrock client wrapper for Claude API calls."""

import json
from time import sleep
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .config import AWSConfig, DEFAULT_AWS_CONFIG


class BedrockClient:
    """Client for interacting with AWS Bedrock Claude models."""

    def __init__(self, config: Optional[AWSConfig] = None):
        self.config = config or DEFAULT_AWS_CONFIG
        self._client = None

    @property
    def client(self):
        """Lazy initialization of boto3 client."""
        if self._client is None:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.config.region
            )
        return self._client

    def generate(
        self,
        prompt: str,
        system_role: str = "You are a helpful assistant.",
        max_retries: int = 4,
        retry_delay_base: int = 5
    ) -> str:
        """
        Generate text using Claude on Bedrock.

        Args:
            prompt: The user prompt to send
            system_role: System message defining Claude's role
            max_retries: Maximum number of retry attempts
            retry_delay_base: Base delay between retries (multiplied by attempt number)

        Returns:
            Generated text response

        Raises:
            RuntimeError: If generation fails after all retries
        """
        for attempt in range(1, max_retries + 1):
            try:
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

                response = self.client.invoke_model(
                    modelId=self.config.model_id,
                    body=json.dumps(request_body)
                )

                model_response = json.loads(response["body"].read())
                return model_response["content"][0]["text"]

            except ClientError as e:
                error_code = e.response['Error']['Code']
                print(f"AWS ClientError on attempt {attempt}: {error_code}")

                if error_code in ['ThrottlingException', 'ServiceUnavailableException', 'InternalServerError']:
                    if attempt < max_retries:
                        sleep(retry_delay_base * attempt)
                        continue
                else:
                    raise RuntimeError(f"Non-retryable error: {error_code}") from e

            except Exception as e:
                print(f"Unexpected error on attempt {attempt}: {e}")
                if attempt < max_retries:
                    sleep(retry_delay_base * attempt)
                    continue

        raise RuntimeError(f"Failed to generate after {max_retries} attempts")
