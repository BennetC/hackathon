"""Council strategy: n agents value the claim, a chief decides coverage and whom to trust,
code turns that into (a, b) with parameters fitted on settled games.

In game (one `price()` call):
  1. All agents (roster.AGENTS) run in parallel on the whole case.
  2. The first agent to answer is published at once (interim PUT), corrected by its own
     fitted drift: the fallback if everything after it fails.
  3. When all agents are back (or the agent budget is spent), their blend is published.
  4. The chief reads the raw verdicts (labelled A, B, C: no model names, no calibration)
     and returns per line P(legit) and which agents' prices are sound.
  5. Final quotes: combine the trusted agents' corrected estimates, then quote (a, b).
After the final PUT the pipeline calls `on_submitted`, which stores the game's raw record.
After settlement the listener calls `on_game_settled`, which refits state.json.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone

from claimbot.evaluation.settlement import decode, load_cached, save_cached, transactions_dir
from claimbot.llm import LLMRequest, make_llm
from claimbot.models import Case, LinePrice
from claimbot.preprocessing.images import prepare_photos
from claimbot.strategies.base import LineValuation, PublishFn, Strategy, StrategyResult
from claimbot.strategies.council import prompts
from claimbot.strategies.council.calibrate import Estimate, combine, fit_all, quote
from claimbot.strategies.council.roster import (
    AGENTS,
    CHIEF,
    CHIEF_BUDGET_S,
    COUNCIL_VERSION,
    DEADLINE_SLACK_S,
    MAX_PHOTOS,
    MIN_CHIEF_S,
    AgentSpec,
)
from claimbot.strategies.council.state import CouncilState, CouncilStore, merge_fit

log = logging.getLogger("claimbot.council")

LABELS = "ABCDEFGHIJ"
AGENT_FIELDS = ("covered", "related", "fair_mid", "reasoning")


class Council(Strategy):
    name = "council"

    def __init__(self, settings, agents: tuple[AgentSpec, ...] = AGENTS,
                 chief: AgentSpec | None = CHIEF, clients: dict | None = None):
        super().__init__(settings)
        self.agents = tuple(agents)
        self.chief = chief
        self.team = getattr(settings, "team_name", "FDN")
        self.store = CouncilStore(settings.runs_dir / "council")
        self.tx_dir = transactions_dir(settings.runs_dir)
        self._clients: dict[str, object] = dict(clients or {})
        self._lock = threading.Lock()
        self._pending: dict[int, dict] = {}
        self.state: CouncilState = self.store.load_state(COUNCIL_VERSION)
        log.info("council %s: %s | chief %s | state %s", COUNCIL_VERSION,
                 ", ".join(f"{a.id}={a.provider}:{a.model}/{a.effort}" for a in self.agents),
                 f"{chief.provider}:{chief.model}/{chief.effort}" if chief else "none",
                 self.state.summary())

    # ---- LLM plumbing -------------------------------------------------------------------

    def _client(self, spec: AgentSpec):
        with self._lock:
            if spec.key not in self._clients:
                self._clients[spec.key] = make_llm(spec.provider, model=spec.model,
                                                   effort=spec.effort)
            return self._clients[spec.key]

    def _call(self, spec: AgentSpec, ctx: str, task: str, schema: dict, until: float,
              images: list) -> tuple[dict | None, float, str | None]:
        t0 = time.time()
        timeout = until - t0
        if timeout < 2.0:
            return None, 0.0, "no time left"
        try:
            req = LLMRequest(shared_context=ctx, task=task, schema=schema,
                             schema_name=spec.id, model=spec.model, effort=spec.effort,
                             max_tokens=spec.max_tokens, timeout_s=timeout, images=images)
            out = self._client(spec).complete_json(req)
            log.info("%s answered in %.1fs", spec.id, time.time() - t0)
            return out, time.time() - t0, None
        except Exception as exc:
            log.warning("%s failed after %.1fs: %s", spec.id, time.time() - t0, exc)
            return None, time.time() - t0, str(exc)[:300]

    # ---- estimates -> quotes --------------------------------------------------------------

    def _estimates(self, record: dict, lines: list[int], use_chief: bool,
                   only: str | None = None) -> dict[int, Estimate]:
        state = self.state
        drifts = {k: state.drift(k) for k in record["agents"]}
        out = {}
        for i in lines:
            verdicts = {k: ag["lines"][str(i)] for k, ag in record["agents"].items()
                        if str(i) in ag.get("lines", {}) and (only is None or k == only)}
            chief = None
            if use_chief and record.get("chief"):
                chief = record["chief"]["lines"].get(str(i))
            est = combine(verdicts, drifts, None if only else state.final, chief)
            if est:
                out[i] = est
        return out

    def _quotes(self, estimates: dict[int, Estimate], source: str, record: dict,
                t0: float) -> StrategyResult:
        quotes, vals, info = [], [], {}
        for i, est in sorted(estimates.items()):
            a, b, m = quote(est, self.state.reject)
            quotes.append(LinePrice(i, a, b))
            spread = 1.645 * est.sigma
            vals.append(LineValuation(index=i, covered=est.p_excl < 0.5, related=None,
                                      low=est.t_hat * math.exp(-spread),
                                      fair=est.t_hat,
                                      high=est.t_hat * math.exp(spread),
                                      reason=f"{source}: p_excl={est.p_excl:.2f} "
                                             f"sigma={est.sigma:.2f} used={est.used}"))
            info[str(i)] = {**est.to_dict(), "a": round(a, 2), "b": round(b, 2),
                            "markup": round(m, 3)}
        record["stages"].append({"source": source, "at_s": round(time.time() - t0, 2),
                                 "lines": info})
        return StrategyResult(quotes=quotes, valuations=vals)

    # ---- the game ---------------------------------------------------------------------------

    def price(self, case: Case, deadline_ts: float,
              publish: PublishFn | None = None) -> StrategyResult:
        t0 = time.time()
        if self.store.state_changed():
            self.state = self.store.load_state(COUNCIL_VERSION)
        lines = [li.index for li in case.lines]
        record = {
            "game_id": case.game_id, "council_version": COUNCIL_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "state_revision": self.state.revision, "lines": lines,
            "agents": {}, "failed": {}, "chief": None, "labels": {},
            "stages": [], "source": None,
        }
        with self._lock:
            self._pending[case.game_id] = record
        if not lines:
            return StrategyResult(trace=record)

        soft = deadline_ts - DEADLINE_SLACK_S
        chief_by = soft - CHIEF_BUDGET_S if self.chief else soft
        ctx = prompts.build_shared_context(case)
        photos = prepare_photos(list(case.photos[:MAX_PHOTOS]),
                                case.directory / "_council_photos")
        valid = set(lines)
        pool = ThreadPoolExecutor(len(self.agents) + 1, thread_name_prefix="council")
        result = StrategyResult()
        try:
            futs = {pool.submit(self._call, spec, ctx,
                                prompts.agent_task(case, spec, len(photos) if spec.photos else 0),
                                prompts.AGENT_SCHEMA, soft - 0.5,
                                photos if spec.photos else []): spec
                    for spec in self.agents}
            published_first = False
            while futs:
                until = chief_by if record["agents"] else soft
                done, _ = wait(list(futs), timeout=max(0.0, until - time.time()),
                               return_when=FIRST_COMPLETED)
                if not done:
                    break
                for fut in done:
                    spec = futs.pop(fut)
                    answer, elapsed, err = fut.result()
                    parsed = _agent_lines(answer, valid)
                    if not parsed:
                        record["failed"][spec.key] = {"elapsed_s": round(elapsed, 1),
                                                      "error": err or "no usable lines"}
                        continue
                    record["agents"][spec.key] = {
                        "provider": spec.provider, "model": spec.model, "effort": spec.effort,
                        "elapsed_s": round(elapsed, 1),
                        "case_notes": (answer or {}).get("case_notes", ""), "lines": parsed}
                    if not published_first:
                        published_first = True
                        result = self._quotes(self._estimates(record, lines, False, spec.key),
                                              f"agent:{spec.id}", record, t0)
                        record["source"] = f"agent:{spec.id}"
                        if publish and result.quotes:
                            publish(result)
            for spec in futs.values():
                record["failed"][spec.key] = {"elapsed_s": round(time.time() - t0, 1),
                                              "error": "missed the agent budget"}
            if not record["agents"]:
                log.error("no agent answered; the fallback quotes stand")
                return StrategyResult(trace=record)

            if len(record["agents"]) > 1:
                result = self._quotes(self._estimates(record, lines, False), "blend",
                                      record, t0)
                record["source"] = "blend"
                if publish and result.quotes:
                    publish(result)

            if self.chief and soft - time.time() >= MIN_CHIEF_S:
                if self._run_chief(case, ctx, record, soft, valid):
                    result = self._quotes(self._estimates(record, lines, True), "chief",
                                          record, t0)
                    record["source"] = "chief"
            elif self.chief:
                log.warning("%.1fs left: skipping the chief", soft - time.time())
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        record["elapsed_s"] = round(time.time() - t0, 2)
        record["token_usage"] = {k: c.take_usage() for k, c in self._clients.items()
                                 if hasattr(c, "take_usage")}
        for q in result.quotes:
            info = record["stages"][-1]["lines"][str(q.index)]
            log.info("line %d [%s] t~%.2f sigma=%.2f p_excl=%.2f m=%.2f -> a=%.2f b=%.2f",
                     q.index, record["source"], info["t_hat"], info["sigma"],
                     info["p_excl"], info["markup"], q.a, q.b)
        result.trace = record
        return result

    def _run_chief(self, case: Case, ctx: str, record: dict, soft: float,
                   valid: set[int]) -> bool:
        keys = list(record["agents"])
        labels = {LABELS[n]: k for n, k in enumerate(keys)}
        record["labels"] = labels
        by_key = {a.key: a for a in self.agents}
        verdicts = {lab: {"case_notes": record["agents"][k]["case_notes"],
                          "lines": [{"index": int(i), **v}
                                    for i, v in record["agents"][k]["lines"].items()]}
                    for lab, k in labels.items()}
        focus = {lab: prompts.focus_summary(by_key[k]) if k in by_key else "general review"
                 for lab, k in labels.items()}
        answer, elapsed, err = self._call(
            self.chief, ctx, prompts.chief_task(case, verdicts, focus),
            prompts.chief_schema(list(labels)), soft - 0.5, [])
        lines = {}
        for v in (answer or {}).get("lines", []) or []:
            try:
                i = int(v.get("index"))
            except (TypeError, ValueError):
                continue
            if i in valid and str(i) not in lines:
                lines[str(i)] = {"legit": v.get("legit"),
                                 "trust": [labels[x] for x in v.get("trust") or [] if x in labels],
                                 "reasoning": v.get("reasoning", "")}
        record["chief"] = {"elapsed_s": round(elapsed, 1), "error": err,
                           "case_notes": (answer or {}).get("case_notes", ""),
                           "lines": lines} if lines else None
        if not lines:
            record["failed"][self.chief.key] = {"elapsed_s": round(elapsed, 1),
                                                "error": err or "no usable lines"}
        return bool(lines)

    # ---- after the game ----------------------------------------------------------------------

    def on_submitted(self, game_id: int, quotes: list[LinePrice], dry_run: bool) -> None:
        with self._lock:
            record = self._pending.pop(game_id, None)
        if record is None or game_id == 0:
            return
        record["dry_run"] = dry_run
        record["submitted"] = [q._asdict() for q in quotes]
        self.store.save_game(record)

    def on_game_settled(self, game_id: int, transactions: list[dict]) -> None:
        if transactions and load_cached(self.tx_dir, game_id) is None:
            save_cached(self.tx_dir, game_id, transactions)
        self.refit()

    def refit(self) -> CouncilState:
        records = self.store.load_games(COUNCIL_VERSION)
        outcomes = {}
        for g in records:
            txns = load_cached(self.tx_dir, g)
            if txns:
                outcomes[g] = decode(txns, self.team)
        fit = fit_all(records, outcomes, [a.key for a in self.agents])
        state = merge_fit(fit, self.state, COUNCIL_VERSION)
        self.store.save_state(state)
        self.state = state
        log.info("council refit: %s", state.summary())
        log.info("b replay: %s", state.diagnostics.get("b_replay"))
        return state


def _agent_lines(answer: dict | None, valid: set[int]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for v in (answer or {}).get("lines", []) or []:
        try:
            i = int(v.get("index"))
        except (TypeError, ValueError):
            continue
        if i in valid and str(i) not in out:
            out[str(i)] = {k: v.get(k) for k in AGENT_FIELDS}
    return out
