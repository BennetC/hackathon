"""Council strategy: n agents + a chief estimate t; fitted coefficients turn it into (a, b).

    roster.py     who sits on the council (models, focus, versions) and the time budget
    prompts.py    what they read and the JSON they answer with
    calibrate.py  drift fits, opponents' reject curve, combining agents, quoting (a, b)
    state.py      runs/council/: game records and the fitted state.json
    strategy.py   the Strategy: price() in game, on_submitted / on_game_settled after
"""

from claimbot.strategies.council.strategy import Council

__all__ = ["Council"]
