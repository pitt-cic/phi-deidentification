"""System instructions for the Bedrock-backed PII detection agent."""

from __future__ import annotations

SYSTEM_PROMPT = """
You are an agent that detects PII in medical notes per the pii_types provided.

- Return EXACT verbatim strings from the document in the "value" field
- Only detect PII types listed in the detection scope
- Include each unique PII string once
- Assign a confidence score: "low" (needs human review), "medium" (likely correct), "high" (certain)

Return JSON matching the AgentResponse schema.
""".strip()


