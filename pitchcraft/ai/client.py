"""Thin wrapper around the Anthropic SDK for structured JSON calls."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5 (best accuracy)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (faster, cheaper)",
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, u: Any) -> None:
        for k in vars(self):
            setattr(self, k, getattr(self, k) + (getattr(u, k, 0) or 0))


class JSONModel(Protocol):
    def call(self, *, system: str, content: list[dict], schema: dict, cache_prefix_blocks: int = 0) -> tuple[dict, Usage]: ...


class ClaudeJSON:
    """Calls Claude with adaptive thinking and a JSON schema output."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, effort: str = "high"):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AIError("No Anthropic API key. Add one in Settings or set ANTHROPIC_API_KEY.")
        if model not in MODELS:
            raise AIError(f"Unsupported model {model}")
        self.client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=900)
        self.model = model
        self.effort = effort

    def call(self, *, system: str, content: list[dict], schema: dict, cache_prefix_blocks: int = 0) -> tuple[dict, Usage]:
        content = [dict(b) for b in content]
        if cache_prefix_blocks and len(content) >= cache_prefix_blocks:
            # cache the stable prefix (outline + attachments) across plan/review calls
            content[cache_prefix_blocks - 1]["cache_control"] = {"type": "ephemeral"}
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=128000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": schema}},
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
            ) as stream:
                msg = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise AIError("The API key was rejected. Check it in Settings.") from e
        except anthropic.RateLimitError as e:
            raise AIError("Rate limited by the Anthropic API. Try again in a minute.") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AIError("Could not reach the Anthropic API.") from e

        usage = Usage()
        usage.add(msg.usage)
        if msg.stop_reason == "refusal":
            raise AIError("The model declined this request.")
        if msg.stop_reason == "max_tokens":
            raise AIError("The plan was too long and got cut off. Split the request into smaller parts.")
        text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise AIError("The model returned no plan.")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError as e:
            raise AIError("The model returned malformed JSON.") from e
