"""Provider-neutral LLM backends sharing one base class (`LLMBackend`) and canonical schemas.

Instantiate any backend directly to switch provider or model:
    from claimbot.llm import (
        AntigravityBackend,
        AnthropicBackend,
        ClaudeCodeBackend,
        CodexBackend,
        VALUATION_SCHEMA,
        PRICING_SCHEMA,
    )

    llm = AntigravityBackend(model="gemini-4-neon-low")
    llm = CodexBackend(model="gpt-6-luna", effort="high")
    llm = ClaudeCodeBackend(model="opus", effort="high")
    llm = AnthropicBackend(model="claude-opus-5-5", effort="high")

Or construct by provider name via `make_llm(provider, model=..., effort=...)`.
"""

from __future__ import annotations

from typing import Protocol

from claimbot.llm.base import (
    LLMBackend,
    LLMError,
    LLMRequest,
    PRICING_LINE_SCHEMA,
    PRICING_SCHEMA,
    VALUATION_LINE_SCHEMA,
    VALUATION_SCHEMA,
)


class LLMClient(Protocol):
    name: str

    def complete_json(self, req: LLMRequest) -> dict: ...


def make_llm(
    provider: str,
    *,
    model: str | None = None,
    effort: str | None = None,
) -> LLMBackend:
    """Instantiate a backend by provider name (`anthropic | claude_code | codex | antigravity`)."""
    p = provider.strip().lower()
    if p == "anthropic":
        from claimbot.llm.anthropic_backend import AnthropicBackend
        return AnthropicBackend(model=model, effort=effort)
    if p == "claude_code":
        from claimbot.llm.cli_backends import ClaudeCodeBackend
        return ClaudeCodeBackend(model=model, effort=effort)
    if p == "codex":
        from claimbot.llm.cli_backends import CodexBackend
        return CodexBackend(model=model, effort=effort)
    if p == "antigravity":
        from claimbot.llm.antigravity_backend import AntigravityBackend
        return AntigravityBackend(model=model, effort=effort)
    raise LLMError(
        f"unknown provider {provider!r} (anthropic | claude_code | codex | antigravity)"
    )


def __getattr__(name: str):
    """Lazy attribute exports so `from claimbot.llm import AntigravityBackend, ...` works cleanly."""
    mapping = {
        "AntigravityBackend": ("claimbot.llm.antigravity_backend", "AntigravityBackend"),
        "AntigravityLLM": ("claimbot.llm.antigravity_backend", "AntigravityBackend"),
        "AnthropicBackend": ("claimbot.llm.anthropic_backend", "AnthropicBackend"),
        "AnthropicLLM": ("claimbot.llm.anthropic_backend", "AnthropicBackend"),
        "ClaudeCodeBackend": ("claimbot.llm.cli_backends", "ClaudeCodeBackend"),
        "ClaudeCodeLLM": ("claimbot.llm.cli_backends", "ClaudeCodeBackend"),
        "CodexBackend": ("claimbot.llm.cli_backends", "CodexBackend"),
        "CodexLLM": ("claimbot.llm.cli_backends", "CodexBackend"),
    }
    if name in mapping:
        import importlib
        mod_name, attr = mapping[name]
        return getattr(importlib.import_module(mod_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLMBackend",
    "LLMClient",
    "LLMError",
    "LLMRequest",
    "PRICING_LINE_SCHEMA",
    "PRICING_SCHEMA",
    "VALUATION_LINE_SCHEMA",
    "VALUATION_SCHEMA",
    "make_llm",
]
