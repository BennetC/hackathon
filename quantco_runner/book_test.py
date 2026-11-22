#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Held-out test of the pricing book: one Opus 5.5 call per case, book built only from earlier cases.

usage: uv run --script book_test.py <first_test_game> <last_test_game> [--book-upto N] [--effort xhigh]
modes: book (pricing book in the prompt) and plain (same prompt, no book) for comparison. Never submits.
"""
import argparse, json, math, pathlib, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from memo_writer import case_inputs  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "book_test"
RANGES = json.loads((HERE / "all_ranges.json").read_text())

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "covered", "fair_gross_total", "basis"],
        "properties": {"index": {"type": "integer"}, "covered": {"type": "boolean"},
                       "fair_gross_total": {"type": "number"}, "basis": {"type": "string"}}}}},
}

INSTRUCTIONS = """You are a senior claims adjuster at a German property insurer. A new claim arrives: policy, damage
description, invoice (line items without prices) and possibly photos.

For every invoice line, give t = the most a claims expert would accept as fair for the WHOLE line, in EUR GROSS
(incl. 19% VAT, total for the stated quantity, never per unit). t = 0 if the line is not covered by the policy, not
related to the reported damage, or excluded (e.g. maintenance done while on site, claim paperwork, upgrades).
Apply contract rules that change the amount (percentage reductions, sub-limits, like-for-like standard grade).

Your answer is used to set prices, so precision matters: being above t counts as an inflated price, being far below
t leaves money on the table. Give your single best estimate of t, not a cautious low number."""

BOOK_HOWTO = """You also get a PRICING BOOK built from earlier claims in this same series. Each entry is one past
invoice line: item, quantity/unit, scope, t~ (the expert's accepted gross total, calibrated against what was
actually judged fair and inflated) with its evidence range, a transferable unit rate, and a note.
How to use it:
- It is the best evidence you have of how THESE experts price. Prefer it over your general market knowledge.
- Find the closest past items (same trade, same kind of work or goods) and scale by quantity, size and grade using
  the unit rates. The same item can appear several times: look at all of them.
- Notes flag when a past t was cut by that case's contract (e.g. 50% reduction, sub-limit). Use the underlying
  price, then apply the CURRENT policy's rules.
- Lines marked "paid 0 here (coverage)" carry no price signal; coverage depends on the current policy, not on them.
- Prices of the same item vary between cases, so treat matches as calibration, not as exact quotes.
In "basis" name the book entries (case/line) or rates you used, in a few words."""


def run(g, mode, book, effort):
    text, imgs = case_inputs(HERE / "decrypted" / f"case_{g:03d}")
    sys_part = INSTRUCTIONS + ("\n\n" + BOOK_HOWTO + f"\n\n<pricing_book>\n{book}\n</pricing_book>" if mode == "book" else
                               "\n\nIn \"basis\" give the rate or reference you used, in a few words.")
    blocks = imgs + [{"type": "text", "text": f"{sys_part}\n\n<claim>\n{text}\n</claim>"}]
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}) + "\n"
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", "claude-opus-5-5", "--effort", effort, "--json-schema", json.dumps(SCHEMA),
           "--strict-mcp-config", "--no-session-persistence", "--tools", ""]
    t = time.perf_counter()
    p = subprocess.run(cmd, input=msg, capture_output=True, text=True, timeout=900, cwd="/tmp")
    dur = time.perf_counter() - t
    ev = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    res = [e for e in ev if e.get("type") == "result"]
    if not res or res[-1].get("is_error"):
        return g, mode, dur, None, str(res[-1].get("result") if res else p.stderr[-300:])[:150]
    out = res[-1].get("structured_output") or json.loads(res[-1]["result"])
    u = res[-1].get("usage") or {}
    OUT.mkdir(exist_ok=True)
    (OUT / f"{mode}_g{g}.json").write_text(json.dumps({"game": g, "mode": mode, "seconds": dur, "usage": u,
                                                       "answer": out}, indent=1, ensure_ascii=False))
    return g, mode, dur, out, None


def score(f, lo, hi):
    v = "high" if f >= hi else ("low" if f < lo else "in")
    if v == "in": return v, 0.0
    edge = hi if v == "high" else lo
    return v, abs(math.log((f + 10) / (edge + 10)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first", type=int); ap.add_argument("last", type=int)
    ap.add_argument("--book-upto", type=int, default=None)
    ap.add_argument("--effort", default="xhigh")
    a = ap.parse_args()
    upto = a.book_upto or a.first - 1
    book = "".join((HERE / "pricing" / f"case_{g:03d}.md").read_text() + "\n" for g in range(1, upto + 1)
                   if (HERE / "pricing" / f"case_{g:03d}.md").exists())
    print(f"book: cases 1-{upto}, ~{len(book) // 4} tokens", flush=True)
    jobs = [(g, m) for g in range(a.first, a.last + 1) for m in ("book", "plain")]
    with ThreadPoolExecutor(len(jobs)) as ex:
        results = list(ex.map(lambda j: run(j[0], j[1], book, a.effort), jobs))

    tot = {m: {"in": 0, "high": 0, "low": 0, "err": 0.0, "n": 0, "secs": []} for m in ("book", "plain")}
    table = {}
    for g, m, dur, out, err in results:
        tot[m]["secs"].append(dur)
        if err:
            print(f"g{g} {m}: FAILED {err}"); continue
        rg = RANGES.get(str(g), {})
        for L in out["lines"]:
            r = rg.get(str(L["index"]))
            if not r or (r[0] == 0 and math.isinf(r[1])):  # no information
                continue
            v, e = score(L["fair_gross_total"], *r)
            tot[m][v] += 1; tot[m]["err"] += e; tot[m]["n"] += 1
            table.setdefault((g, L["index"]), {"range": r})[m] = (L["fair_gross_total"], v, L["basis"])
    print(f"\n{'mode':6} {'lines':>5} {'in':>4} {'high':>5} {'low':>4} {'in%':>5} {'mean|log err|':>14} {'secs (max)':>11}")
    for m, t in tot.items():
        n = max(t["n"], 1)
        print(f"{m:6} {t['n']:5} {t['in']:4} {t['high']:5} {t['low']:4} {100 * t['in'] / n:5.0f} {t['err'] / n:14.3f} "
              f"{sum(t['secs']) / len(t['secs']):5.0f} ({max(t['secs']):.0f})")
    print()
    for (g, i), row in sorted(table.items()):
        lo, hi = row["range"]
        cells = "  ".join(f"{m}={row[m][0]:>8.0f} {row[m][1]:4}" if m in row else f"{m}=  -" for m in ("book", "plain"))
        print(f"g{g} L{i:<2} range=[{lo:>8.2f}, {hi:>8.2f})  {cells}   | {row.get('book', (0, 0, ''))[2][:90]}")


if __name__ == "__main__":
    main()
