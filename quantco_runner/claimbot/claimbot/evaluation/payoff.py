"""Exact payoff rules, for offline evaluation of strategies (docs/agents/01-game-rules.md)."""

from __future__ import annotations

from itertools import permutations


def settle(a: float, b: float, t: float, c: float) -> float:
    """Amount the insurer (bid b) pays the handyman (charge a) for one line."""
    if a <= b:  # accepted
        return a if a <= t else min(a, c)
    return 1.5 * a if a <= t else 0.0  # rejected


def round_net(quotes: dict[str, tuple[float, float]], t: float, c: float) -> dict[str, float]:
    """Net payoff per team for one line where quotes = {team: (a, b)}; everyone plays everyone."""
    net = {team: 0.0 for team in quotes}
    for issuer, reviewer in permutations(quotes, 2):
        pay = settle(quotes[issuer][0], quotes[reviewer][1], t, c)
        net[issuer] += pay
        net[reviewer] -= pay
    return net
