"""One game, end to end: key → decrypt → parse → fallback submit → strategy → final submit → bench upload.

Every stage is timestamped relative to the run start and written to
runs/game_NNN/<utc-stamp>/{run.log, report.json}. The pipeline never raises: any
failure is logged and recorded, and whatever could be submitted has been submitted.
"""

from __future__ import annotations

import inspect
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from claimbot.api import ApiError, ClaimApi
from claimbot.config import Settings
from claimbot.evaluation.bench import build_prediction, push_run
from claimbot.logs import run_log_file
from claimbot.models import Case, LinePrice, as_line_price
from claimbot.preprocessing import decrypt, expected_zip, find_zip_for_key, key_opens, load_case
from claimbot.strategies import LineValuation, Strategy, StrategyResult

log = logging.getLogger("claimbot.pipeline")


def utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class RunReport:
    game_id: int
    run_dir: str
    started_at: str
    start_time: str | None
    strategy: str
    dry_run: bool
    stages: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    case: dict = field(default_factory=dict)
    fallback_quotes: list[dict] = field(default_factory=list)
    interim_quotes: list[dict] = field(default_factory=list)
    final_quotes: list[dict] = field(default_factory=list)
    submissions: list[dict] = field(default_factory=list)
    fallback_submitted: bool = False
    final_submitted: bool = False
    bench_uploaded: bool = False
    bench_response: dict | None = None

    @property
    def ok(self) -> bool:
        return self.final_submitted or (self.dry_run and bool(self.final_quotes))


class Timeline:
    def __init__(self, report: RunReport, start_ts: float | None):
        self.report = report
        self.t0 = time.time()
        self.start_ts = start_ts

    def mark(self, stage: str, ok: bool = True, **detail) -> None:
        now = time.time()
        entry = {
            "stage": stage,
            "ok": ok,
            "at": utc_iso(now),
            "since_run_start_s": round(now - self.t0, 3),
        }
        if self.start_ts is not None:
            entry["since_game_start_s"] = round(now - self.start_ts, 3)
        entry.update(detail)
        self.report.stages.append(entry)
        rel = f"+{entry['since_run_start_s']:.3f}s"
        if "since_game_start_s" in entry:
            rel += f" (T{entry['since_game_start_s']:+.3f}s)"
        extra = " ".join(f"{k}={v}" for k, v in detail.items())
        (log.info if ok else log.error)("[%s] %-18s %s %s", rel, stage, "ok " if ok else "FAIL", extra)


def fetch_key(api: ClaimApi, game_id: int, start_ts: float | None, retry_s: float,
              poll_s: float = 1.0, early_s: float = 0.5) -> str:
    """The key is only released at start_time (403 before). Start polling `early_s`
    before start to absorb clock skew, every `poll_s`: a handful of requests, never a flood."""
    if start_ts is not None:
        wait = start_ts - early_s - time.time()
        if wait > 0:
            log.info("game %d: first key request in %.2f s", game_id, wait)
            time.sleep(wait)
    give_up = max(time.time(), start_ts or 0.0) + retry_s
    attempt = 0
    while True:
        attempt += 1
        try:
            key = api.get_key(game_id)
            if start_ts is not None:
                log.info("key received on attempt %d at T%+.3f s", attempt, time.time() - start_ts)
            return key
        except ApiError as exc:
            if exc.status == 403 and time.time() < give_up:
                log.debug("key attempt %d: 403 (not released yet), retry in %.2f s", attempt, poll_s)
                time.sleep(poll_s)
                continue
            raise


def fallback_prices(case: Case | None, settings: Settings) -> list[LinePrice]:
    if case is not None and case.lines:
        indexes = [li.index for li in case.lines]
    elif settings.fallback_line_count > 0:
        indexes = list(range(1, settings.fallback_line_count + 1))
    else:
        return []
    return [
        LinePrice(i, settings.fallback_charge, settings.fallback_limit)
        for i in indexes
    ]


def merge(fallback: list[LinePrice], strategy_prices) -> list[LinePrice]:
    """Strategy (index, a, b) triples override the fallback; unknown indexes are dropped."""
    by_index = {q.index: q for q in fallback}
    known = set(by_index)
    for raw in strategy_prices or []:
        try:
            q = as_line_price(raw)
        except Exception as exc:
            log.warning("ignoring malformed strategy output %r: %s", raw, exc)
            continue
        if known and q.index not in known:
            log.warning("strategy quoted unknown line %d; ignoring", q.index)
            continue
        by_index[q.index] = q
    return [by_index[i] for i in sorted(by_index)]


def _submit(api: ClaimApi, game_id: int, quotes: list[LinePrice], label: str,
            report: RunReport, tl: Timeline) -> bool:
    payload = [q.to_api() for q in quotes]
    try:
        resp = api.submit(game_id, payload)
    except Exception as exc:
        report.errors.append(f"{label} submit: {exc}")
        tl.mark(f"submit_{label}", ok=False, error=str(exc)[:200])
        return False
    stored = {int(r.get("line_item_index", -1)) for r in resp if isinstance(r, dict)}
    missing = sorted({p["index"] for p in payload} - stored)
    report.submissions.append({"label": label, "at": utc_iso(time.time()),
                               "request": payload, "response": resp})
    tl.mark(f"submit_{label}", ok=not missing, lines=len(payload), missing=missing or None)
    return not missing


def _accepts_publish(strategy) -> bool:
    try:
        return "publish" in inspect.signature(strategy.price).parameters
    except (TypeError, ValueError):
        return False


def run_game(
    game_id: int,
    settings: Settings,
    api: ClaimApi,
    strategy: Strategy,
    *,
    start_ts: float | None = None,
    submit: bool = True,
    key: str | None = None,
    zip_path: Path | None = None,
    enforce_deadline: bool = True,
    upload_bench: bool | None = None,
) -> RunReport:
    """Run one game. `start_ts` = official start (None in debug: window simulated from now)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = settings.runs_dir / f"game_{game_id:03d}" / stamp
    report = RunReport(
        game_id=game_id,
        run_dir=str(run_dir),
        started_at=utc_iso(time.time()),
        start_time=utc_iso(start_ts) if start_ts else None,
        strategy=getattr(strategy, "name", type(strategy).__name__),
        dry_run=not submit,
    )
    should_upload_bench = settings.bench_upload if upload_bench is None else bool(upload_bench)
    with run_log_file(run_dir / "run.log"):
        log.info("=== game %d | strategy=%s | submit=%s | bench=%s | run_dir=%s",
                 game_id, report.strategy, submit, should_upload_bench, run_dir)
        tl = Timeline(report, start_ts)
        try:
            _run(game_id, settings, api, strategy, report, tl, run_dir,
                 start_ts, submit, key, zip_path, enforce_deadline, should_upload_bench)
        except Exception as exc:  # last line of defence: never crash the listener
            log.exception("unexpected pipeline error")
            report.errors.append(f"unexpected: {exc!r}")
            tl.mark("crash", ok=False, error=repr(exc)[:200])
        tl.mark("done", ok=report.ok, errors=len(report.errors))
        (run_dir / "report.json").write_text(json.dumps(asdict(report), indent=2, default=str))
    return report


def _run(game_id, settings, api, strategy, report, tl, run_dir,
         start_ts, submit, key, zip_path, enforce_deadline, should_upload_bench) -> None:
    # 1. Key
    if key is None:
        try:
            key = fetch_key(api, game_id, start_ts, settings.key_retry_s,
                            settings.key_poll_s, settings.key_early_s)
        except Exception as exc:
            report.errors.append(f"key: {exc}")
            tl.mark("key", ok=False, error=str(exc)[:200])
            return
        tl.mark("key", source="api")
    else:
        tl.mark("key", source="given")

    # Deadline for the strategy: official window, or simulated from now in debug runs.
    window_start = start_ts if (start_ts is not None) else time.time()
    if enforce_deadline:
        deadline = window_start + settings.game_window_s - settings.submit_margin_s
    else:
        deadline = time.time() + 3600
    log.info("strategy deadline %s (%.1fs from now)", utc_iso(deadline), deadline - time.time())

    # 2. Locate + decrypt the archive
    expected = zip_path or expected_zip(settings.cases_dir, settings.case_file_template, game_id)
    chosen = expected if expected.exists() and key_opens(expected, key) else None
    if chosen is None:
        log.warning("%s missing or key does not open it; scanning %s", expected, settings.cases_dir)
        chosen = find_zip_for_key(settings.cases_dir, key, skip=expected)
    if chosen is None:
        report.errors.append("no local archive opens with this key")
        tl.mark("locate_zip", ok=False, expected=str(expected))
        _fallback_only(api, game_id, None, settings, report, tl, submit)
        return
    tl.mark("locate_zip", file=chosen.name, matches_expected=chosen == expected)

    case_dir = run_dir / "case"
    try:
        files = decrypt(chosen, key, case_dir)
    except Exception as exc:
        report.errors.append(f"decrypt: {exc}")
        tl.mark("decrypt", ok=False, error=str(exc)[:200])
        _fallback_only(api, game_id, None, settings, report, tl, submit)
        return
    tl.mark("decrypt", files=[f.name for f in files])

    # 3. Parse
    try:
        case = load_case(game_id, case_dir)
    except Exception as exc:
        report.errors.append(f"parse: {exc}")
        tl.mark("parse", ok=False, error=str(exc)[:200])
        _fallback_only(api, game_id, None, settings, report, tl, submit)
        return
    report.case = {
        "zip": chosen.name,
        "policy_chars": len(case.policy),
        "description": case.description[:2000],
        "invoice_chars": len(case.invoice_text),
        "photos": [p.name for p in case.photos],
        "lines": [asdict(li) for li in case.lines],
    }
    tl.mark("parse", lines=len(case.lines), photos=len(case.photos))
    if not case.lines:
        report.errors.append("invoice parser found no line items")
        log.error("no line items parsed; see %s/invoices.pdf", case_dir)

    # 4. Fallback submission right away (last write wins, so the strategy can overwrite it)
    fallback = fallback_prices(case, settings)
    report.fallback_quotes = [q._asdict() for q in fallback]
    if fallback and submit:
        report.fallback_submitted = _submit(api, game_id, fallback, "fallback", report, tl)

    # 5. Strategy under a hard time limit
    strategy_quotes = None
    strategy_valuations: list[LineValuation] = []
    strategy_trace = None
    budget = deadline - time.time()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="strategy")
    kwargs = {}
    finalising = threading.Event()  # once set, late interim submissions are dropped
    last_interim: list = []         # best result so far if the strategy later times out
    last_interim_valuations: list[LineValuation] = []
    if _accepts_publish(strategy):
        def publish(prices) -> None:
            """Interim submission from inside the strategy before its final result arrives."""
            if finalising.is_set():
                log.warning("interim result arrived after the final step started; dropped")
                return
            if isinstance(prices, StrategyResult):
                raw_prices = prices.quotes
                last_interim_valuations[:] = list(prices.valuations)
            else:
                raw_prices = prices
            interim = merge(fallback, raw_prices)
            last_interim[:] = interim
            report.interim_quotes = [q._asdict() for q in interim]
            if submit and interim and time.time() < window_start + settings.game_window_s:
                _submit(api, game_id, interim, "interim", report, tl)
            else:
                tl.mark("submit_interim", skipped="dry run" if not submit else "window closed",
                        lines=len(interim))
        kwargs["publish"] = publish
    t_strat_start = time.monotonic()
    strategy_latency_ms: float | None = None
    try:
        fut = pool.submit(strategy.price, case, deadline, **kwargs)
        raw_result = fut.result(timeout=max(0.0, budget))
        strategy_latency_ms = round((time.monotonic() - t_strat_start) * 1000.0, 1)
        if isinstance(raw_result, StrategyResult):
            strategy_quotes = raw_result.quotes
            strategy_valuations = list(raw_result.valuations)
            strategy_trace = raw_result.to_trace_dict() or getattr(strategy, "last_trace", None)
        else:
            strategy_quotes = raw_result
            strategy_trace = getattr(strategy, "last_trace", None)
        tl.mark("strategy", lines=len(strategy_quotes or []), budget_s=round(budget, 2))
    except FutureTimeout:
        strategy_latency_ms = round((time.monotonic() - t_strat_start) * 1000.0, 1)
        report.errors.append("strategy timed out")
        tl.mark("strategy", ok=False, error="timeout", budget_s=round(budget, 2))
    except Exception as exc:
        strategy_latency_ms = round((time.monotonic() - t_strat_start) * 1000.0, 1)
        log.exception("strategy raised")
        report.errors.append(f"strategy: {exc!r}")
        tl.mark("strategy", ok=False, error=repr(exc)[:200])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    finalising.set()

    if strategy_quotes is None and last_interim:
        log.warning("strategy gave no final result; keeping its interim result")
        strategy_quotes = list(last_interim)
        if not strategy_valuations and last_interim_valuations:
            strategy_valuations = list(last_interim_valuations)
    final = merge(fallback, strategy_quotes)
    report.final_quotes = [q._asdict() for q in final]
    for q in final:
        log.info("line %3d  a=%10.2f  b=%10.2f", q.index, q.a, q.b)

    # 6. Final submission
    if not final:
        report.errors.append("nothing to submit")
        tl.mark("submit_final", ok=False, error="no quotes")
        return
    if not submit:
        tl.mark("submit_final", skipped="dry run", lines=len(final))
    else:
        if start_ts is not None and time.time() > start_ts + settings.game_window_s:
            log.warning("past the 60 s window; submitting anyway (server will likely refuse)")
        report.final_submitted = _submit(api, game_id, final, "final", report, tl)

    # 7. Logs, strictly after the submission so they never cost time inside the window
    if strategy_trace:
        try:
            (run_dir / "strategy_trace.json").write_text(
                json.dumps(strategy_trace, indent=2, default=str)
            )
        except Exception as exc:
            log.warning("could not write strategy trace: %s", exc)
    on_submitted = getattr(strategy, "on_submitted", None)
    if callable(on_submitted):
        try:
            on_submitted(game_id, final, not submit)
        except Exception as exc:
            log.warning("strategy on_submitted failed: %s", exc)

    # 8. Optional FDN Bench upload (runs strictly after QuantCo submission so it never risks the 60 s window)
    if should_upload_bench:
        _upload_bench(
            game_id,
            final,
            strategy_valuations,
            strategy_latency_ms,
            settings,
            report,
            tl,
        )


def _upload_bench(
    game_id: int,
    quotes: list[LinePrice],
    valuations: list[LineValuation],
    latency_ms: float | None,
    settings: Settings,
    report: RunReport,
    tl: Timeline,
) -> None:
    if game_id == 0:
        tl.mark("upload_bench", skipped="game 0")
        return
    if not settings.bench_token:
        tl.mark("upload_bench", skipped="no token")
        return
    if not quotes:
        tl.mark("upload_bench", skipped="no quotes")
        return
    strategy_name = settings.bench_strategy_name or report.strategy
    pred = build_prediction(game_id, quotes, valuations=valuations, latency_ms=latency_ms)
    try:
        resp = push_run(
            settings.bench_url,
            settings.bench_token,
            strategy_name=strategy_name,
            author=settings.bench_author,
            predictions=[pred],
            timeout_s=settings.http_timeout_s,
        )
    except Exception as exc:
        report.errors.append(f"bench upload: {exc}")
        tl.mark("upload_bench", ok=False, error=str(exc)[:200])
        return
    report.bench_uploaded = True
    report.bench_response = resp
    tl.mark("upload_bench", strategy=strategy_name, lines=len(quotes))


def _fallback_only(api, game_id, case, settings, report, tl, submit) -> None:
    quotes = fallback_prices(case, settings)
    report.final_quotes = [q._asdict() for q in quotes]
    if quotes and submit:
        report.final_submitted = _submit(api, game_id, quotes, "fallback", report, tl)
    elif not quotes:
        log.error("no fallback possible (set CLAIMBOT_FALLBACK_LINE_COUNT to submit blind)")
