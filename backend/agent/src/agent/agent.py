"""Agent wiring for the Bedrock-hosted model using BedrockConverseModel."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
import logfire
from botocore.config import Config
from pydantic_ai import Agent, RunContext, ToolOutput
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.providers.bedrock import BedrockProvider

from agent.models import AgentContext, AgentResponse
from agent.prompt import SYSTEM_PROMPT

# Initialize boto3 session and Bedrock client
# Disable boto3 retries - let worker-level retry handle throttling with proper backoff
session = boto3.Session(region_name=os.environ["AWS_REGION"])
bedrock_config = Config(retries={"max_attempts": 0})
bedrock_client = session.client("bedrock-runtime", config=bedrock_config)

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    if os.getenv("ENVIRONMENT") == 'local':
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        load_dotenv(env_path)
except ImportError:
    # Skip loading .env if python-dotenv is not installed, assuming environment variables are set in the environment
    pass

# Disable Logfire scrubbing for prompt and system_instructions attributes
def _scrubbing_callback(m: logfire.ScrubMatch):
    return m.value

_scrubbing_options = logfire.ScrubbingOptions(callback=_scrubbing_callback)

# Requires `LOGFIRE_TOKEN` env variable to be set in dev or prod environment
# For local development, you can run `uv run logfire auth` and `uv run logfire projects use <project_name>`
logfire.configure(scrubbing=_scrubbing_options)

# Get model ID from environment variable
DEFAULT_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
)

# Initialize BedrockConverseModel
bedrock_model = BedrockConverseModel(
    DEFAULT_MODEL_ID,
    provider=BedrockProvider(bedrock_client=bedrock_client),
)

pii_agent = Agent[AgentContext, AgentResponse](
    model=bedrock_model,
    instructions=SYSTEM_PROMPT,
    output_type=ToolOutput(AgentResponse),
)

@pii_agent.instructions
async def add_detection_scope(ctx: RunContext[AgentContext]) -> str:
    """Inject runtime detection parameters into the system prompt."""

    context = ctx.deps
    if context is None:
        return "<detection_scope>No runtime context supplied.</detection_scope>"

    detection = context.detection
    pii_types = ", ".join(detection.pii_types)
    limit = detection.max_entities or "no-limit"
    source_name = context.source_name or "unspecified document"

    return (
        "<detection_scope>"
        f"source={source_name}; "
        f"pii_types={pii_types}; "
        f"max_entities={limit}"
        "</detection_scope>"
    )

