"""The council's maths: per-source drift, the opponents' reject curve, combining agents,
and turning an estimate into (a, b).

Drift. t is never revealed; settled games only bracket it per line (t_lo <= t < t_hi, see
claimbot/evaluation/settlement.py). For each source (every agent, and the final combined
estimate) we model  ln(t / t_hat) ~ N(mu, sigma)  and fit (mu, sigma) by censored maximum
likelihood on those brackets, with a mild prior. Lines can also be worthless (t = 0, not
covered or unrelated); a bracket with no lower bound is then explained either way, so each
line's likelihood is  p_excl * [t_lo == 0] + (1 - p_excl) * P(bracket | mu, sigma).

Combining. Each agent's estimate is corrected by its own bias (z_i = ln t_hat_i - mu_i) and
weighted by 1 / sigma_i^2, over the agents the chief trusts on that line. The final fit then
measures the combined estimate's remaining bias and its spread (agents share inputs, so
their errors are correlated: the combined spread must be measured, not assumed).

Quoting. With p = P(t = 0) and ln(t / t_hat) ~ N(0, sigma) otherwise:
  b = the 1/3 quantile of t      (reject iff P(t >= a) < 2/3; opponents do not matter)
  a = argmax_m  m * [S(m) * (1 + 0.5 F(m)) + (1 - S(m)) * (1 - F(m))],  a = m * t_hat
      S(m) = P(t >= m * t_hat),  F(m) = share of opponents rejecting a markup m,
      m capped near the markups we have actually observed F at.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, ndtr, ndtri

from claimbot.evaluation.settlement import LineOutcome

# ---- priors and knobs --------------------------------------------------------------------
PRIOR_MU_SD = 0.25            # bias: N(0, 0.25) in log space (about +-25 %)
PRIOR_SIGMA = 0.35            # spread prior centre
PRIOR_LOG_SIGMA_SD = 0.5
DRIFT_HALF_LIFE = 30.0        # games; a fixed agent drifts slowly
REJECT_HALF_LIFE = 10.0       # games; opponents change their play
PRIOR_REJECT = 0.45           # measured: opponents reject ~40-50 % regardless of fairness
PRIOR_SLOPE = 1.0             # d logit F / d ln m
PRIOR_REJECT_SD = (1.0, 1.0)  # sd of (alpha, beta)
DAMPING = 0.5                 # move this share of the way to a new fit
B_QUANTILE = 1.0 / 3.0
M_MIN = 0.3
M_CAP_DEFAULT = 1.5           # markup cap before we have seen F anywhere
M_CAP_STEP = 1.25             # never quote more than 25 % above markups seen before
M_CAP_ABS = 2.5               # c >= 4 t, so min(a, c) = a stays true below this
P_CLIP = (0.01, 0.99)


@dataclass
class Drift:
    mu: float = 0.0
    sigma: float = PRIOR_SIGMA
    n: int = 0          # informative lines
    n_lo: int = 0       # ... with a lower bound
    n_hi: int = 0       # ... with an upper bound


@dataclass
class RejectCurve:
    alpha: float = float(np.log(PRIOR_REJECT / (1 - PRIOR_REJECT)))
    beta: float = PRIOR_SLOPE
    n: int = 0
    m_seen: float | None = None   # 90th percentile of markups observed
    m_cap: float = M_CAP_DEFAULT

    def __call__(self, m):
        return expit(self.alpha + self.beta * np.log(m))


@dataclass
class Estimate:
    t_hat: float
    sigma: float
    p_excl: float
    used: list[str] = field(default_factory=list)
    spread: float = 0.0

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _clip(x, lo=0.0, hi=1.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return lo
    return min(hi, max(lo, v)) if math.isfinite(v) else lo


# ---- combining ---------------------------------------------------------------------------

def combine(verdicts: dict[str, dict], drifts: dict[str, Drift], final: Drift | None = None,
            chief: dict | None = None) -> Estimate | None:
    """One line's estimate from agent verdicts (agent key -> line verdict).

    final=None: a single source (the first-agent fallback): its own drift and spread apply.
    chief: {"legit": p, "trust": [agent keys]} or None (then all agents count).
    """
    trust = set(chief.get("trust") or []) if chief else set()
    p_ex = [1.0 - _clip(v.get("covered")) * _clip(v.get("related")) for v in verdicts.values()]

    def gather(only: set[str]):
        zs, ws, keys = [], [], []
        for key, v in verdicts.items():
            mid = _clip(v.get("fair_mid"), 0.0, math.inf)
            if mid <= 0 or (only and key not in only):
                continue
            d = drifts.get(key) or Drift()
            zs.append(math.log(mid) - d.mu)
            ws.append(1.0 / max(d.sigma, 1e-3) ** 2)
            keys.append(key)
        return zs, ws, keys

    zs, ws, keys = gather(trust)
    if not zs and trust:            # the chief trusted nobody with a usable price
        zs, ws, keys = gather(set())
    if not zs:
        return None
    w = np.asarray(ws)
    z = float(np.dot(w, zs) / w.sum())
    spread = float(np.sqrt(np.dot(w, (np.asarray(zs) - z) ** 2) / w.sum())) if len(zs) > 1 else 0.0
    if final is not None:
        t_hat, base = math.exp(z - final.mu), final.sigma
    else:
        t_hat, base = math.exp(z), max((drifts.get(k) or Drift()).sigma for k in keys)
    if chief is not None and chief.get("legit") is not None:
        p = 1.0 - _clip(chief.get("legit"))
    else:
        p = float(np.mean(p_ex)) if p_ex else 0.0
    return Estimate(t_hat=t_hat, sigma=max(base, spread), p_excl=_clip(p, *P_CLIP),
                    used=keys, spread=spread)


# ---- quoting -----------------------------------------------------------------------------

def quote(est: Estimate, curve: RejectCurve) -> tuple[float, float, float]:
    """(a, b, markup) for one line."""
    t, s, p = est.t_hat, max(est.sigma, 1e-3), est.p_excl
    if t <= 0:
        return 0.0, 0.0, 0.0
    q = (B_QUANTILE - p) / (1.0 - p)
    b = 0.0 if q <= 0 else t * math.exp(s * float(ndtri(q)))
    m = np.linspace(M_MIN, max(M_MIN, curve.m_cap), 241)
    S = (1.0 - p) * (1.0 - ndtr(np.log(m) / s))
    F = curve(m)
    income = m * (S * (1.0 + 0.5 * F) + (1.0 - S) * (1.0 - F))
    best = float(m[int(np.argmax(income))])
    return best * t, b, best


# ---- fitting -----------------------------------------------------------------------------

@dataclass
class _Obs:
    lo: list = field(default_factory=list)    # ln(t_lo / t_hat), -inf if none
    hi: list = field(default_factory=list)    # ln(t_hi / t_hat), +inf if none
    pe: list = field(default_factory=list)
    w: list = field(default_factory=list)

    def add(self, out: LineOutcome, t_hat: float, p_excl: float, weight: float) -> None:
        if t_hat <= 0 or (out.t_lo <= 0 and math.isinf(out.t_hi)):
            return
        self.lo.append(math.log(out.t_lo / t_hat) if out.t_lo > 0 else -math.inf)
        self.hi.append(math.log(out.t_hi / t_hat) if math.isfinite(out.t_hi) else math.inf)
        self.pe.append(_clip(p_excl, *P_CLIP))
        self.w.append(weight)


def fit_drift(obs: _Obs) -> Drift:
    if not obs.w:
        return Drift()
    lo, hi = np.asarray(obs.lo), np.asarray(obs.hi)
    pe, w = np.asarray(obs.pe), np.asarray(obs.w)
    lo_zero = np.isneginf(lo)

    def nll(theta):
        mu, ls = theta
        s = math.exp(ls)
        pin = np.clip(ndtr((hi - mu) / s) - ndtr((lo - mu) / s), 1e-12, 1.0)
        like = np.where(lo_zero, pe + (1 - pe) * pin, pin)
        prior = 0.5 * (mu / PRIOR_MU_SD) ** 2 + \
            0.5 * ((ls - math.log(PRIOR_SIGMA)) / PRIOR_LOG_SIGMA_SD) ** 2
        return float(-np.dot(w, np.log(like)) + prior)

    best = None
    for mu0 in (-0.3, 0.0, 0.3):
        r = minimize(nll, x0=[mu0, math.log(PRIOR_SIGMA)], method="L-BFGS-B",
                     bounds=[(-2.0, 2.0), (math.log(0.02), math.log(3.0))])
        if best is None or r.fun < best.fun:
            best = r
    mu, ls = best.x
    return Drift(mu=float(mu), sigma=float(math.exp(ls)), n=len(w),
                 n_lo=int((~lo_zero).sum()), n_hi=int(np.isfinite(hi).sum()))


def fit_reject(x: list[float], y: list[int], w: list[float], m_seen: float | None) -> RejectCurve:
    prior = RejectCurve()
    if not y:
        return prior
    x_, y_, w_ = np.asarray(x), np.asarray(y, float), np.asarray(w)
    a0, b0 = prior.alpha, prior.beta
    sa, sb = PRIOR_REJECT_SD

    def nll(theta):
        a, b = theta
        p = np.clip(expit(a + b * x_), 1e-9, 1 - 1e-9)
        return float(-np.dot(w_, y_ * np.log(p) + (1 - y_) * np.log(1 - p))
                     + 0.5 * ((a - a0) / sa) ** 2 + 0.5 * ((b - b0) / sb) ** 2)

    r = minimize(nll, x0=[a0, b0], method="BFGS")
    alpha, beta = (float(v) for v in r.x)
    cap = M_CAP_DEFAULT if m_seen is None else max(M_CAP_DEFAULT, M_CAP_STEP * m_seen)
    return RejectCurve(alpha=alpha, beta=beta, n=len(y), m_seen=m_seen,
                       m_cap=float(min(M_CAP_ABS, cap)))


def _recency(game: int, latest: int, half_life: float) -> float:
    return 0.5 ** (max(0, latest - game) / half_life)


@dataclass
class FitResult:
    agents: dict[str, Drift]
    final: Drift
    reject: RejectCurve
    games: list[int]
    diagnostics: dict


def line_inputs(record: dict, line: int) -> tuple[dict[str, dict], dict | None]:
    """(agent key -> verdict, chief line or None) for one line of a stored game record."""
    verdicts = {}
    for key, ag in (record.get("agents") or {}).items():
        v = (ag.get("lines") or {}).get(str(line))
        if v:
            verdicts[key] = v
    chief = ((record.get("chief") or {}).get("lines") or {}).get(str(line))
    return verdicts, chief


def fit_all(records: dict[int, dict], outcomes: dict[int, dict[int, LineOutcome]],
            agent_keys: list[str]) -> FitResult:
    """Fit everything from scratch from the stored game records and settled outcomes."""
    games = sorted(g for g in records if g in outcomes)
    latest = max(games, default=0)

    # 1. Each agent on its own.
    agents: dict[str, Drift] = {}
    for key in agent_keys:
        obs = _Obs()
        for g in games:
            w = _recency(g, latest, DRIFT_HALF_LIFE)
            for line, out in outcomes[g].items():
                v = line_inputs(records[g], line)[0].get(key)
                if not v:
                    continue
                p_ex = 1.0 - _clip(v.get("covered")) * _clip(v.get("related"))
                obs.add(out, _clip(v.get("fair_mid"), 0.0, math.inf), p_ex, w)
        agents[key] = fit_drift(obs)

    # 2. The combined estimate, recomputed from raw verdicts with the new agent drifts.
    obs = _Obs()
    unbiased = Drift(mu=0.0, sigma=PRIOR_SIGMA)
    for g in games:
        w = _recency(g, latest, DRIFT_HALF_LIFE)
        for line, out in outcomes[g].items():
            verdicts, chief = line_inputs(records[g], line)
            est = combine(verdicts, agents, unbiased, chief)
            if est:
                obs.add(out, est.t_hat, est.p_excl, w)
    final = fit_drift(obs)

    # 3. Opponents' reject curve against our markup over the final estimate.
    xs, ys, ws, markups = [], [], [], []
    for g in games:
        w = _recency(g, latest, REJECT_HALF_LIFE)
        for line, out in outcomes[g].items():
            if not out.our_a or not out.outgoing:
                continue
            verdicts, chief = line_inputs(records[g], line)
            est = combine(verdicts, agents, final, chief)
            if not est or est.t_hat <= 0:
                continue
            m = out.our_a / est.t_hat
            markups.append(m)
            for o in out.outgoing:
                xs.append(math.log(m))
                ys.append(0 if o.accepted else 1)
                ws.append(w)
    m_seen = float(np.percentile(markups, 90)) if markups else None
    reject = fit_reject(xs, ys, ws, m_seen)

    diagnostics = {"lines_with_bracket": final.n, "markup_lines": len(markups),
                   "b_replay": replay_b(records, outcomes, games, agents, final)}
    return FitResult(agents=agents, final=final, reject=reject, games=games,
                     diagnostics=diagnostics)


def replay_b(records, outcomes, games, agents, final) -> dict:
    """What our incoming bills would have cost with the current b rule, on the bills whose
    fairness the brackets settle, against what we actually paid on them."""
    new_cost = actual = 0.0
    n = undetermined = 0
    for g in games:
        for line, out in outcomes[g].items():
            verdicts, chief = line_inputs(records[g], line)
            est = combine(verdicts, agents, final, chief)
            if not est:
                continue
            b = quote(est, RejectCurve())[1]
            for x in out.incoming:
                if x.a is None:
                    continue
                if x.a <= out.t_lo:
                    fair = True
                elif x.a >= out.t_hi:
                    fair = False
                else:
                    undetermined += 1
                    continue
                n += 1
                actual += x.amount
                new_cost += x.a if x.a <= b else (1.5 * x.a if fair else 0.0)
    return {"bills": n, "undetermined": undetermined, "actual_cost": round(actual, 2),
            "replayed_cost": round(new_cost, 2)}


def damp(new: float, old: float | None, share: float = DAMPING) -> float:
    return new if old is None else old + share * (new - old)
