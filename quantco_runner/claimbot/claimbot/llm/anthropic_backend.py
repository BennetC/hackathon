"""Anthropic (Claude) backend.

- Shared case context goes into `system` with cache_control, so the ~15k-token policy is
  written to the cache once per case and read cheaply by every agent.
- Answers are constrained to a JSON schema via output_config.format.
- Server-side refusal fallbacks are enabled (fallbacks="default").
Env: ANTHROPIC_API_KEY (or an `ant auth login` profile). Defaults: model="claude-opus-5-5",
effort="high".
"""

from __future__ import annotations

import json

import anthropic

from claimbot.llm.base import LLMBackend, LLMError, LLMRequest
from claimbot.preprocessing.images import encode_image

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicBackend(LLMBackend):
    name = "anthropic"
    default_model = DEFAULT_MODEL
    default_effort = "high"

    def __init__(self, model: str | None = None, effort: str | None = None):
        super().__init__(model=model, effort=effort)
        self.client = anthropic.Anthropic(max_retries=1)
        self.usage["cache_write"] = 0

    def _record_anthropic_usage(self, usage) -> None:
        if usage is None:
            return
        self._record_usage(
            input=getattr(usage, "input_tokens", 0) or 0,
            cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cached_input=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output=getattr(usage, "output_tokens", 0) or 0,
        )

    def warm(self, shared_context: str, model: str | None, effort: str, timeout_s: float) -> None:
        """Write the shared case context to the prompt cache before the parallel fan-out
        (max_tokens=0: prefill only, no output billed). Same model/effort as real calls."""
        try:
            resp = self.client.with_options(timeout=timeout_s).beta.messages.create(
                model=model or self.model or self.default_model,
                max_tokens=0,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=[{"type": "text", "text": shared_context,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": "warmup"}],
                output_config={"effort": effort} if effort else {},
            )
            self._record_anthropic_usage(resp.usage)
        except anthropic.APIError as exc:
            raise LLMError(f"anthropic warm: {exc}") from exc

    def complete_json(self, req: LLMRequest) -> dict:
        model = self.resolve_model(req) or self.default_model
        effort = self.resolve_effort(req)
        content: list[dict] = []
        for path in req.images:
            media_type, data = encode_image(path)
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": data}})
        content.append({"type": "text", "text": req.task})
        try:
            resp = self.client.with_options(timeout=req.timeout_s).beta.messages.create(
                model=model,
                max_tokens=req.max_tokens,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=[{"type": "text", "text": req.shared_context,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_config={
                    **({"effort": effort} if effort else {}),
                    "format": {"type": "json_schema", "schema": req.schema},
                },
            )
        except anthropic.APIError as exc:
            raise LLMError(f"anthropic: {exc}") from exc
        self._record_anthropic_usage(resp.usage)
        if resp.stop_reason == "refusal":
            raise LLMError("anthropic: refusal")
        if resp.stop_reason == "max_tokens":
            raise LLMError("anthropic: hit max_tokens")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"anthropic: invalid JSON: {text[:200]!r}") from exc


AnthropicLLM = AnthropicBackend
