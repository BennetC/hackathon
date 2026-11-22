"""The council's files, all under runs/council/:

  games/game_NNN.json   what the council produced for a game (raw agent and chief output,
                        the quotes and the parameters used), written AFTER submitting
  state.json            the fitted parameters the next game quotes with
  snapshots/            state.json as it was after each settled game

Settled transactions are cached by the settlement module under runs/transactions/.
Every fit starts from the raw records, so no fit depends on an earlier fit's adjustments.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from claimbot.strategies.council.calibrate import Drift, FitResult, RejectCurve, damp

log = logging.getLogger("claimbot.council")


@dataclass
class CouncilState:
    council_version: str
    revision: int = 0
    fitted_at: str = ""
    games: list[int] = field(default_factory=list)
    agents: dict[str, Drift] = field(default_factory=dict)
    final: Drift = field(default_factory=Drift)
    reject: RejectCurve = field(default_factory=RejectCurve)
    diagnostics: dict = field(default_factory=dict)

    def drift(self, key: str) -> Drift:
        return self.agents.get(key) or Drift()

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "CouncilState":
        return cls(
            council_version=str(d.get("council_version", "")),
            revision=int(d.get("revision", 0)),
            fitted_at=d.get("fitted_at", ""),
            games=list(d.get("games", [])),
            agents={k: Drift(**v) for k, v in (d.get("agents") or {}).items()},
            final=Drift(**(d.get("final") or {})),
            reject=RejectCurve(**(d.get("reject") or {})),
            diagnostics=d.get("diagnostics") or {},
        )

    def summary(self) -> str:
        parts = [f"rev {self.revision} on {len(self.games)} games"]
        for k, d in self.agents.items():
            parts.append(f"{k}: mu={d.mu:+.3f} sigma={d.sigma:.3f} n={d.n}")
        f, r = self.final, self.reject
        parts.append(f"final: mu={f.mu:+.3f} sigma={f.sigma:.3f} n={f.n}")
        parts.append(f"reject: F(1)={1 / (1 + math.exp(-r.alpha)):.2f} slope={r.beta:.2f} "
                     f"n={r.n} m_cap={r.m_cap:.2f}")
        return " | ".join(parts)


def merge_fit(fit: FitResult, prev: CouncilState | None, council_version: str) -> CouncilState:
    """New state from a fresh fit, damped towards the previous state of the same council."""
    same = prev is not None and prev.council_version == council_version
    agents = {}
    for key, d in fit.agents.items():
        old = prev.agents.get(key) if same else None
        agents[key] = _damp_drift(d, old)
    final = _damp_drift(fit.final, prev.final if same else None)
    r, old_r = fit.reject, (prev.reject if same else None)
    reject = RejectCurve(
        alpha=damp(r.alpha, old_r.alpha if old_r and old_r.n else None),
        beta=damp(r.beta, old_r.beta if old_r and old_r.n else None),
        n=r.n, m_seen=r.m_seen, m_cap=r.m_cap)
    return CouncilState(
        council_version=council_version,
        revision=(prev.revision + 1) if same else 1,
        fitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        games=fit.games, agents=agents, final=final, reject=reject,
        diagnostics=fit.diagnostics)


def _damp_drift(new: Drift, old: Drift | None) -> Drift:
    if old is None or old.n == 0:
        return new
    return Drift(mu=damp(new.mu, old.mu),
                 sigma=math.exp(damp(math.log(new.sigma), math.log(old.sigma))),
                 n=new.n, n_lo=new.n_lo, n_hi=new.n_hi)


class CouncilStore:
    def __init__(self, root: Path):
        self.root = root
        self.games_dir = root / "games"
        self.state_file = root / "state.json"
        self._state_mtime: float | None = None

    # ---- state ------------------------------------------------------------------------
    def load_state(self, council_version: str) -> CouncilState:
        try:
            d = json.loads(self.state_file.read_text())
            state = CouncilState.from_dict(d)
            self._state_mtime = self.state_file.stat().st_mtime
            if state.council_version == council_version:
                return state
            log.warning("state.json is for council %s, not %s: starting from the prior",
                        state.council_version, council_version)
        except FileNotFoundError:
            pass
        except Exception as exc:
            log.error("state.json unreadable (%s): starting from the prior", exc)
        return CouncilState(council_version=council_version)

    def state_changed(self) -> bool:
        try:
            return self.state_file.stat().st_mtime != self._state_mtime
        except FileNotFoundError:
            return False

    def save_state(self, state: CouncilState) -> None:
        _atomic_write(self.state_file, state.to_json())
        self._state_mtime = self.state_file.stat().st_mtime
        if state.games:  # how the fit developed: one snapshot per latest settled game
            _atomic_write(self.root / "snapshots" / f"state_after_game_{max(state.games):03d}.json",
                          state.to_json())

    # ---- game records -----------------------------------------------------------------
    def game_file(self, game_id: int) -> Path:
        return self.games_dir / f"game_{game_id:03d}.json"

    def save_game(self, record: dict) -> bool:
        """A dry run (backtest) never replaces a live record of the same council."""
        path = self.game_file(int(record["game_id"]))
        if path.exists() and record.get("dry_run"):
            try:
                old = json.loads(path.read_text())
                if not old.get("dry_run") and old.get("council_version") == record.get(
                        "council_version"):
                    log.info("keeping the live record of game %s", record["game_id"])
                    return False
            except Exception:
                pass
        _atomic_write(path, json.dumps(record, indent=2, default=str))
        return True

    def load_games(self, council_version: str) -> dict[int, dict]:
        out = {}
        for path in sorted(self.games_dir.glob("game_*.json")):
            try:
                rec = json.loads(path.read_text())
            except Exception as exc:
                log.warning("skipping %s: %s", path.name, exc)
                continue
            if rec.get("council_version") == council_version:
                out[int(rec["game_id"])] = rec
        return out


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)
