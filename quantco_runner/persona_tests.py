#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Blind single-case tests of two prompt styles. Never submits.

  web       minimal role prompt + WebSearch/WebFetch, model researches prices/rules itself
  adjuster  how a German claims adjuster (Schadenregulierer) works + one worked example (practice case 0), no tools

usage: uv run --script persona_tests.py <game> --mode web|adjuster [--effort xhigh]
"""
import argparse, json, pathlib, pickle, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from memo_writer import case_inputs  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "persona_tests"

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "covered", "fair_gross_total", "why", "sources"],
        "properties": {"index": {"type": "integer"}, "covered": {"type": "boolean"},
                       "fair_gross_total": {"type": "number"}, "why": {"type": "string"},
                       "sources": {"type": "array", "items": {"type": "string"}}}}}},
}

FORMAT = """For every invoice line give the fair GROSS total in EUR (incl. VAT, for the whole line, not per unit) that
you would pay, or 0 if the line is not covered by the policy or not related to the damage. The invoice has no prices."""

WEB = f"""You work as a claims adjuster at a German property insurer. A policyholder sent in the claim below.
{FORMAT}
Research the web for whatever helps you get the best answer: current German market prices for the goods and work,
typical trade hourly rates, how such clauses are usually applied. In "sources" list the URLs you relied on."""

ADJUSTER = f"""You are an experienced German Schadenregulierer (claims adjuster) at a property insurer. {FORMAT}

How you work, line by line:
1. Coverage. Read the policy first: which perils are insured, which costs, which exclusions, sub-limits and
   deductions. If the line's cause or cost type is not insured, or an exclusion hits, the answer is 0. A line that
   bundles covered and uncovered work without a split is judged by its main purpose.
2. Causality. Compare the line with the damage description and photos. Work in undamaged areas, upgrades, routine
   maintenance done "while on site", duplicated work, and claim paperwork are not part of the loss: 0.
3. Quantity. Check the amount and unit are plausible for the described damage (hours for the job, m2 vs the patch
   size, number of units actually damaged).
4. Price. Use what a German adjuster would check against: trade hourly rates (plumber / electrician / tiler about
   EUR 60-95 net per hour, region-dependent), standard repair times, like-for-like replacement at standard grade
   (not list price of a premium model, no upgrades), small-job minimum effort, call-out fees only when tied to
   covered work.
5. Contract math. Apply contractual reductions (e.g. a percentage cut for missing protection) after the
   like-for-like value, then sub-limits. Add 19% VAT; the answer is the gross total of the whole line.
6. Your number is the most an expert would still accept as fair. Not the cheapest possible quote, not the invoice
   the tradesperson hoped for.

Worked example (practice case, method only, the numbers are illustrative):
Policy: escape of water from fractured supply pipes; insured costs = locating the leak and opening/closing the wall,
repairing the pipe, restoring plaster and tiles to previous condition; exclusion = maintenance, servicing or
descaling of installations, even if done during the same visit. Damage: copper pipe split inside the bathroom wall;
plumber opened the wall, replaced the section, re-plastered and re-tiled the patch; also serviced the gas boiler.
- Line 1 "Leak detection and opening of the bathroom wall", 2 hrs: covered (2.1). 2 h is plausible. 2 h x ~EUR 80
  net = 160, +19% VAT = ~EUR 190.
- Line 2 "Replacement of split 15 mm copper pipe section incl. fittings", 1 pcs: covered (2.2). Small part plus
  fitting work, ~EUR 100 net = ~EUR 120 gross.
- Line 3 "Closing the opening, re-plastering and re-tiling approx. 0.2 m2": covered (2.3). Tiny area, so the
  small-job minimum dominates, not a per-m2 rate: ~EUR 150 net = ~EUR 180 gross.
- Line 4 "Annual service and descaling of the gas boiler": excluded (3.1) and unrelated to the leak: 0.

Now handle the claim below the same way and give your best estimate. In "sources" name the clauses you applied."""


def run(blocks, effort, tools, timeout=1200):
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}) + "\n"
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", "claude-opus-5-5", "--effort", effort, "--json-schema", json.dumps(SCHEMA),
           "--strict-mcp-config", "--no-session-persistence", "--tools", ",".join(tools)]
    if tools:
        cmd += ["--allowedTools", *tools]
    t = time.perf_counter()
    p = subprocess.run(cmd, input=msg, capture_output=True, text=True, timeout=timeout, cwd="/tmp")
    ev = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    res = [e for e in ev if e.get("type") == "result"]
    if not res or res[-1].get("is_error"):
        sys.exit(f"claude failed rc={p.returncode}: {(res[-1].get('result') if res else p.stderr[-500:])}")
    calls = [c["name"] for e in ev if e.get("type") == "assistant"
             for c in e["message"].get("content", []) if c.get("type") == "tool_use"]
    r = res[-1]
    return (r.get("structured_output") or json.loads(r["result"])), time.perf_counter() - t, calls, r.get("usage") or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game", type=int)
    ap.add_argument("--mode", choices=["web", "adjuster"], required=True)
    ap.add_argument("--effort", default="xhigh")
    a = ap.parse_args()

    text, imgs = case_inputs(HERE / "decrypted" / f"case_{a.game:03d}")
    lines, _ = pickle.load(open(HERE / "research/s4-imitate-404/lines.pkl", "rb"))
    ranges = {L["line"]: L["bound"] for L in lines if L["g"] == a.game}

    prompt, tools = (WEB, ["WebSearch", "WebFetch"]) if a.mode == "web" else (ADJUSTER, [])
    out, dur, calls, u = run(imgs + [{"type": "text", "text": f"{prompt}\n\n<claim>\n{text}\n</claim>"}], a.effort, tools)

    OUT.mkdir(exist_ok=True)
    (OUT / f"{a.mode}_g{a.game}.json").write_text(json.dumps(
        {"game": a.game, "mode": a.mode, "seconds": dur, "tool_calls": calls, "usage": u, "ranges": ranges,
         "answer": out}, indent=1, ensure_ascii=False))
    print(f"[{a.mode}] game {a.game}: {dur:.0f}s, tool calls={len(calls)} {dict((c, calls.count(c)) for c in set(calls))}, "
          f"out_tokens={u.get('output_tokens')}")
    for L in sorted(out["lines"], key=lambda x: x["index"]):
        lo, hi = ranges.get(L["index"], (None, None))
        f = L["fair_gross_total"]
        verdict = "?" if lo is None else ("IN RANGE" if lo <= f < hi else ("too high (fraud)" if f >= hi else "too low"))
        print(f"\nline {L['index']}: covered={L['covered']} fair={f:g}  range=[{lo:g}, {hi:g})  -> {verdict}")
        print(f"  why: {L['why']}")
        if L["sources"]:
            print("  sources: " + "; ".join(L["sources"]))


if __name__ == "__main__":
    main()
