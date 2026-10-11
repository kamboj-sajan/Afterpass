"""Builds the agent's model from `AGENT_MODEL` (brief §10.1).

`AGENT_MODEL` is `provider:model_id`:
- `mantle:<id>` uses Amazon Bedrock's OpenAI-compatible endpoint, signed with the caller's AWS
  credentials. This is what the account can invoke today.
- `bedrock` (or `bedrock:<id>`) uses Bedrock's Converse API with `BEDROCK_MODEL_ID`, for a
  Claude model once the account has quota for one.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "mantle:openai.gpt-oss-120b"
MAX_OUTPUT_TOKENS = 600
# Open-weight models on the OpenAI-compatible endpoint think before they answer, and that
# thinking is billed and capped as output. The answer itself is held to MAX_OUTPUT_TOKENS by
# the prompt's 120-word limit; this is the room allowed for both.
MANTLE_COMPLETION_TOKENS = 2000


def model_name() -> str:
    spec = os.environ.get("AGENT_MODEL") or DEFAULT_MODEL
    provider, _, model_id = spec.partition(":")
    if provider == "bedrock" and not model_id:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "")
    return f"{provider}:{model_id}"


def build_model():
    """The Strands model for the configured provider."""
    provider, _, model_id = model_name().partition(":")
    region = os.environ.get("AWS_REGION", "us-west-2")
    if not model_id:
        raise RuntimeError("AGENT_MODEL names no model, and BEDROCK_MODEL_ID is not set.")
    if provider == "mantle":
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            bedrock_mantle_config={"region": region},
            client_args={"timeout": 50.0, "max_retries": 1},
            model_id=model_id,
            params={"max_completion_tokens": MANTLE_COMPLETION_TOKENS, "temperature": 0.0},
        )
    if provider == "bedrock":
        from strands.models import BedrockModel

        return BedrockModel(
            model_id=model_id, region_name=region, max_tokens=MAX_OUTPUT_TOKENS, temperature=0.0
        )
    raise RuntimeError(f"Unknown AGENT_MODEL provider '{provider}'. Use mantle or bedrock.")
