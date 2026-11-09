"""Ask the LLM for claims, as structured output through a forced tool call."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

PROMPT = Path(__file__).parent / "prompts" / "summary.md"
DEFAULT_MODEL = "claude-haiku-5-5"

TOOL = {
    "name": "report_claims",
    "description": "Report the summary as a list of claims, each citing one fact.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "metric_id": {"type": "string"},
                        "value": {"type": ["number", "string"]},
                    },
                    "required": ["text", "metric_id", "value"],
                },
            }
        },
        "required": ["claims"],
    },
}


def write_summary(facts: list[dict], month: date, client=None, model: str | None = None) -> list[dict]:
    if client is None:
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    response = client.messages.create(
        model=model or os.getenv("LLM_MODEL", DEFAULT_MODEL),
        max_tokens=1500,
        system=PROMPT.read_text(),
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "report_claims"},
        messages=[{
            "role": "user",
            "content": f"Reference month: {month:%B %Y}.\n\nFacts:\n{json.dumps(facts, indent=2, ensure_ascii=False)}",
        }],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    return block.input["claims"]
