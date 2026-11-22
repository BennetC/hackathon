"""Replay a staged organizer case entirely offline with a cached released key."""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pyzipper.zipfile import BadZipFile

from case_pipeline import _save, case_manifest, extract_case, inspection_input, process_case
from invoice_rows import DEFAULT_VAT_RATE, checked_vat
from pricing import DEFAULT_SPREAD_BPS
from quantco_fetch import schedule_starts
from simulate_local import replay, wire_items
from strategy import STRATEGY_CUTOFF, STRATEGY_DOC_CHARS, run_strategy, strategy_script


CACHE = Path(__file__).resolve().parent / ".cache" / "quantco"


def synthetic_scenario(prices):
    """Create reproducible opponents and thresholds for an offline mechanics check."""
    items = []
    for line in prices["items"]:
        limit = line["limit_cents"]
        threshold = limit * 11 // 10
        items.append({
            "index": line["item_id"],
            "threshold_cents": threshold,
            "cap_cents": max(4 * threshold, 10_000),
            "opponents": [
                {"charge_cents": limit, "limit_cents": limit},
                {"charge_cents": threshold, "limit_cents": 0},
                {"charge_cents": threshold + 1, "limit_cents": 0},
            ],
        })
    return {"items": items}


def offline_replay(
    game_id, archive, password_file, schedule, output, *,
    vat_rate=DEFAULT_VAT_RATE, analysis_file=None, spread_bps=DEFAULT_SPREAD_BPS, strategy=None,
):
    started = time.monotonic()
    release = schedule_starts(json.loads(schedule.read_text(encoding="utf-8")))[game_id]
    if datetime.now(timezone.utc) < release:
        raise ValueError("case is still ahead of release on the saved schedule")
    if archive.name != f"case_{game_id:03d}.zip":
        raise ValueError("archive name must match the organizer's case number")
    if not 1 <= spread_bps <= 10_000:
        raise ValueError("spread must be between 1 and 10000 basis points")
    checked_vat(vat_rate)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    stage = time.monotonic()
    unpacked = output / "case"
    extract_case(archive, unpacked, password_file.read_bytes().rstrip(b"\r\n"), require_encrypted=True)
    extracted = time.monotonic()
    manifest = case_manifest(unpacked, game_id, vat_rate=vat_rate)
    parsed = time.monotonic()
    _save(output, "manifest.json", manifest)
    ids = manifest["expected_item_ids"]
    if strategy is not None:
        evidence = inspection_input(manifest, unpacked, max_doc_chars=STRATEGY_DOC_CHARS)
        strategy_start = time.monotonic()
        prices, payload = asyncio.run(run_strategy(
            strategy, game_id, unpacked, evidence, ids, STRATEGY_CUTOFF - (strategy_start - started),
        ))
        _save(output, "evidence.json", evidence)
        _save(output, "strategy-prices.json", prices)
        _save(output, "strategy-wire.json", payload)
        timings = {
            "archive_ms": round(1000 * (extracted - stage), 2),
            "invoice_ms": round(1000 * (parsed - extracted), 2),
            "strategy_ms": round(1000 * (time.monotonic() - strategy_start), 2),
            "total_ms": round(1000 * (time.monotonic() - started), 2),
        }
        _save(output, "run.json", {"game_id": game_id, "rows": len(ids), "timings": timings})
        return len(ids), timings
    runs = output / "prices"
    result = process_case(manifest, runs, analysis_file=analysis_file, spread_bps=spread_bps)
    if "baseline" not in result["payloads"]:
        raise ValueError("failed to build a complete deterministic baseline")
    baseline = json.loads((runs / "baseline.json").read_text(encoding="utf-8"))
    scenario = synthetic_scenario(baseline)
    timings = {
        "archive_ms": round(1000 * (extracted - stage), 2),
        "invoice_ms": round(1000 * (parsed - extracted), 2),
        "baseline_ms": result["baseline_ms"],
    }
    final = {"scenario": "synthetic", "baseline": replay(baseline, scenario)}
    _save(output, "baseline-wire.json", wire_items(baseline, expected_ids=ids))
    if "refined" in result["payloads"]:
        refined = json.loads((runs / "refined.json").read_text(encoding="utf-8"))
        _save(output, "refined-wire.json", wire_items(refined, expected_ids=ids))
        final["refined"] = replay(refined, scenario)
    _save(output, "evidence.json", inspection_input(manifest, unpacked))
    _save(output, "synthetic-scenario.json", scenario)
    _save(output, "offline-payoffs.json", final)
    timings["total_ms"] = round(1000 * (time.monotonic() - started), 2)
    _save(output, "run.json", {
        "game_id": game_id,
        "scheduled_start": release.isoformat(),
        "rows": len(ids),
        "valuation": "refined_available" if "refined" in final else "baseline",
        "assessment": (
            "used" if "refined" in final else "invalid_or_unreadable" if analysis_file else "absent"
        ),
        "timings": timings,
    })
    return len(ids), timings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=int)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--schedule", type=Path, default=CACHE / "games.json")
    parser.add_argument("--output", type=Path, required=True, help="fresh path inside .cache/quantco")
    analysis = parser.add_mutually_exclusive_group()
    analysis.add_argument("--analysis-file", type=Path)
    analysis.add_argument("--strategy", help="replay a teammate's analysis and pricing script")
    parser.add_argument("--vat-rate", type=Decimal, default=DEFAULT_VAT_RATE)
    parser.add_argument("--spread-bps", type=int, default=DEFAULT_SPREAD_BPS)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(CACHE) or output == CACHE:
        parser.error("output must be a fresh subdirectory of .cache/quantco")
    try:
        strategy = strategy_script(args.strategy) if args.strategy is not None else None
        count, times = offline_replay(
            args.game, args.archive, args.password_file or CACHE / f"game-{args.game}.password",
            args.schedule, output, vat_rate=args.vat_rate, analysis_file=args.analysis_file,
            spread_bps=args.spread_bps, strategy=strategy,
        )
    except (ArithmeticError, BadZipFile, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        parser.exit(1, f"offline replay failed ({type(exc).__name__})\n")
    print(f"Offline replay complete for Game {args.game}: {count} rows in {times['total_ms']:.2f} ms")


if __name__ == "__main__":
    main()
