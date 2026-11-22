"""Shared base class, request type, and canonical schemas for all LLM backends.

Every backend (`AntigravityBackend`, `ClaudeCodeBackend`, `CodexBackend`, `AnthropicBackend`)
subclasses `LLMBackend`, shares the same constructor (`model`, `effort`), and shares the same
`complete_json(LLMRequest) -> dict` / `ask(...) -> dict` contract.

Switching models or providers is a one-line swap:
    llm = AntigravityBackend(model="gemini-4-neon-low")
    llm = AntigravityBackend(model="gemini-3.8-flash-high")
    llm = CodexBackend(model="gpt-6-luna", effort="high")
    llm = ClaudeCodeBackend(model="opus", effort="high")
    llm = AnthropicBackend(model="claude-opus-5-5", effort="high")

What a backend returns:
    A backend is a pure LLM transport — it does NOT compute `(a, b)` or own strategy logic.
    `complete_json(req)` / `ask(...)` returns the parsed Python `dict` matching `req.schema`
    (defaulting to `VALUATION_SCHEMA`). Token accounting is tracked separately via `take_usage()`.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


class LLMError(RuntimeError):
    """Raised when an LLM backend call fails, times out, or returns invalid JSON."""


# ---- Shared canonical JSON schemas --------------------------------------------------------

VALUATION_LINE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "index",
        "description",
        "covered",
        "related",
        "fair_gross_total",
        "low",
        "high",
    ],
    "properties": {
        "index": {"type": "integer"},
        "description": {"type": "string"},
        "covered": {"type": "boolean"},
        "related": {"type": "boolean"},
        "fair_gross_total": {"type": "number"},
        "low": {"type": "number"},
        "high": {"type": "number"},
    },
}

VALUATION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines"],
    "properties": {
        "lines": {"type": "array", "items": VALUATION_LINE_SCHEMA},
    },
}

PRICING_LINE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["index", "a", "b", "reason"],
    "properties": {
        "index": {"type": "integer"},
        "a": {"type": "number"},
        "b": {"type": "number"},
        "reason": {"type": "string"},
    },
}

PRICING_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines"],
    "properties": {
        "lines": {"type": "array", "items": PRICING_LINE_SCHEMA},
    },
}


# ---- Request & shared base class ----------------------------------------------------------


@dataclass
class LLMRequest:
    shared_context: str = ""                             # cacheable prefix / system context
    task: str = ""                                       # per-call user prompt / task
    schema: dict = field(default_factory=lambda: VALUATION_SCHEMA)  # JSON Schema for the returned dict
    schema_name: str = "answer"
    model: str | None = None                             # None -> use backend.model
    effort: str | None = None                            # None -> use backend.effort
    max_tokens: int = 16000
    timeout_s: float = 40.0
    images: list[Path] = field(default_factory=list)


class LLMBackend(ABC):
    """Common abstract base class for all LLM backends."""

    name: ClassVar[str] = ""
    default_model: ClassVar[str | None] = None
    default_effort: ClassVar[str | None] = None

    def __init__(self, model: str | None = None, effort: str | None = None):
        self.model: str | None = model if model is not None else self.default_model
        self.effort: str | None = effort if effort is not None else self.default_effort
        self._lock = threading.Lock()
        self.usage: dict[str, int] = {
            "calls": 0,
            "input": 0,
            "cached_input": 0,
            "output": 0,
        }

    def resolve_model(self, req: LLMRequest) -> str | None:
        return req.model if req.model is not None else self.model

    def resolve_effort(self, req: LLMRequest) -> str | None:
        return req.effort if req.effort is not None else self.effort

    def _record_usage(self, **kw: int | None) -> None:
        with self._lock:
            self.usage["calls"] += 1
            for k, v in kw.items():
                self.usage[k] = self.usage.get(k, 0) + int(v or 0)

    def take_usage(self) -> dict[str, int]:
        with self._lock:
            out = dict(self.usage)
            for k in self.usage:
                self.usage[k] = 0
        return out

    @abstractmethod
    def complete_json(self, req: LLMRequest) -> dict:
        """Execute one structured-JSON call and return the parsed dict matching `req.schema`."""

    def ask(
        self,
        task: str,
        *,
        shared_context: str = "",
        schema: dict | None = None,
        schema_name: str = "answer",
        images: list[Path] | None = None,
        timeout_s: float = 40.0,
        model: str | None = None,
        effort: str | None = None,
        max_tokens: int = 16000,
    ) -> dict:
        """Convenience wrapper around `complete_json` using this backend's model/effort and shared schema."""
        return self.complete_json(
            LLMRequest(
                shared_context=shared_context,
                task=task,
                schema=schema if schema is not None else VALUATION_SCHEMA,
                schema_name=schema_name,
                model=model,
                effort=effort,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
                images=list(images or []),
            )
        )

    def close(self) -> None:
        """Release any persistent subprocesses or connections held by the backend."""

    def __enter__(self) -> "LLMBackend":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
