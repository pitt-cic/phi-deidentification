"""Agent wiring for the Bedrock-hosted model using BedrockConverseModel."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import logfire
from pydantic_ai import Agent, RunContext, ToolOutput
from pydantic_ai.models.bedrock import BedrockConverseModel

from agent.models import AgentContext, AgentResponse
from agent.prompt import SYSTEM_PROMPT

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Disable Logfire scrubbing for prompt and system_instructions attributes
def scrubbing_callback(m: logfire.ScrubMatch):
    if (
        m.path == ('attributes', 'user_prompt')
        and m.pattern_match.group(0) == 'Credential'
    ):
        return m.value

    if (
        m.path == ('attributes', 'system_instructions')
        and m.pattern_match.group(0) == 'ssn'
    ):
        return m.value

scrubbing_options = logfire.ScrubbingOptions(callback=scrubbing_callback)

logfire_api_key = os.getenv("LOGFIRE_API_KEY")
logfire_project = os.getenv("LOGFIRE_PROJECT")
if logfire_api_key:
    if logfire_project:
        logfire.configure(api_key=logfire_api_key, project_name=logfire_project, scrubbing=scrubbing_options)
    else:
        logfire.configure(api_key=logfire_api_key, scrubbing=scrubbing_options)
else:
    if logfire_project:
        logfire.configure(project_name=logfire_project, scrubbing=scrubbing_options)
    else:
        logfire.configure(scrubbing=scrubbing_options)

# Get AWS region from environment or use default
aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

if not os.getenv("AWS_REGION") and not os.getenv("AWS_DEFAULT_REGION"):
    os.environ["AWS_DEFAULT_REGION"] = aws_region

# Get model ID from environment variable
DEFAULT_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
)

# Initialize BedrockConverseModel
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
    source_name = context.source_name or "unspecified document"

    return (
        "<detection_scope>"
        f"source={source_name}; "
        f"pii_types={pii_types}; "
        f"max_entities={limit}"
        "</detection_scope>"
    )

