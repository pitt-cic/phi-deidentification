"""Agent wiring for the Bedrock-hosted model using BedrockConverseModel."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext, ToolOutput
from pydantic_ai.models.bedrock import BedrockConverseModel

from agent.models import AgentContext, AgentResponse
from agent.prompt import SYSTEM_PROMPT

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Get AWS region from environment or use default
aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

# Ensure AWS_DEFAULT_REGION is set for BedrockConverseModel
# Only set if neither AWS_REGION nor AWS_DEFAULT_REGION is already set
if not os.getenv("AWS_REGION") and not os.getenv("AWS_DEFAULT_REGION"):
    os.environ["AWS_DEFAULT_REGION"] = aws_region

# Get model ID from environment variable
DEFAULT_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
)

# Initialize BedrockConverseModel - uses AWS credentials from environment or boto3 default chain
# The model will use the region from AWS_REGION/AWS_DEFAULT_REGION environment variable or boto3 default
bedrock_model = BedrockConverseModel(DEFAULT_MODEL_ID)

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
    confidence = (
        "include confidence scores (0.0-1.0) and reasons" if detection.include_confidence else "omit confidence scores and reasons"
    )
    source_name = context.source_name or "unspecified document"

    return (
        "<detection_scope>"
        f"source={source_name}; "
        f"pii_types={pii_types}; "
        f"max_entities={limit}; "
        f"{confidence}."
        "</detection_scope>"
    )

