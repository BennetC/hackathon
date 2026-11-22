"""Pricing strategies registry and super-class exports.

Select a registered strategy by name (`CLAIMBOT_STRATEGY=council` or `--strategy council`)
or dynamically via `package.module:ClassName`.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from claimbot.strategies.base import LineValuation, PublishFn, Strategy, StrategyResult
from claimbot.strategies.council import Council

if TYPE_CHECKING:
    from claimbot.config import Settings

REGISTRY: dict[str, type[Strategy]] = {
    "council": Council,
}


def load_strategy(spec: str, settings: "Settings") -> Strategy:
    if spec in REGISTRY:
        return REGISTRY[spec](settings)
    if ":" not in spec:
        raise ValueError(
            f"unknown strategy {spec!r}; use one of {sorted(REGISTRY)} or module:Class"
        )
    module_name, cls_name = spec.split(":", 1)
    cls = getattr(importlib.import_module(module_name), cls_name)
    return cls(settings)


__all__ = [
    "Council",
    "LineValuation",
    "PublishFn",
    "REGISTRY",
    "Strategy",
    "StrategyResult",
    "load_strategy",
]
