from __future__ import annotations

import os

from dotenv import load_dotenv
import logfire
from pydantic_ai import Agent, RunContext, ToolOutput
from pydantic_ai.models.bedrock import BedrockConverseModel

from agent.models import AgentContext, AgentResponse
from agent.prompt import SYSTEM_PROMPT

load_dotenv()


def _scrubbing_callback(m: logfire.ScrubMatch):
    return m.value

_scrubbing_options = logfire.ScrubbingOptions(callback=_scrubbing_callback)

# Requires `LOGFIRE_TOKEN` env variable to be set
logfire.configure(scrubbing=_scrubbing_options)

aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
if not os.getenv("AWS_REGION") and not os.getenv("AWS_DEFAULT_REGION"):
    os.environ["AWS_DEFAULT_REGION"] = aws_region

DEFAULT_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
bedrock_model = BedrockConverseModel(DEFAULT_MODEL_ID)

pii_agent = Agent[AgentContext, AgentResponse](
    model=bedrock_model,
    instructions=SYSTEM_PROMPT,
    output_type=ToolOutput(AgentResponse),
)

@pii_agent.instructions
async def add_detection_scope(ctx: RunContext[AgentContext]) -> str:
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

