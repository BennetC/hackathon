#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Pricing book: per past case, one compact pricing entry per invoice line, calibrated to the market range for t.

Coverage/policy is NOT the goal here; entries are about what each exact thing is worth.
usage: uv run --script pricing_writer.py <from> <to> [--effort high] [--jobs 4]
writes pricing/case_NNN.json + pricing/case_NNN.md, and pricing/PRICING_BOOK.md (all cases)
"""
import argparse, json, math, pathlib, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from memo_writer import case_inputs  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "pricing"
RANGES = json.loads((HERE / "all_ranges.json").read_text())

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["context", "lines"],
    "properties": {
        "context": {"type": "string"},
        "lines": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["index", "item", "quantity", "unit", "scope", "price", "unit_rate", "note"],
            "properties": {
                "index": {"type": "integer"},
                "item": {"type": "string"}, "quantity": {"type": "number"}, "unit": {"type": "string"},
                "scope": {"type": "string"}, "price": {"type": "number"},
                "unit_rate": {"type": "string"}, "note": {"type": "string"}}}}},
}

TASK = """You are building a pricing book from past insurance claims. A later model will use it to price new invoice
lines, so it needs to know what each exact thing was worth to the claims expert. Coverage questions are handled
elsewhere: focus on prices.

For the case below you get the files and, per invoice line, the market range for t = the most the expert would pay
for the whole line, GROSS incl. VAT. How to read [lo, hi): a charge of lo was judged fair (t >= lo) and a charge of
hi was judged inflated (t < hi). hi = inf: no upper evidence. lo = 0: no lower evidence. [0, small) like [0, 6):
the expert paid ~0 for this line (not covered/unrelated) so it carries no price information.

Write:
- context: one sentence: trade, region if stated, kind of damage (e.g. "Munich plumber, burst pipe in bathroom").
- per line:
  item: the exact thing, with the specs that drive price (size, brand/grade, material, model if visible in photos).
  quantity, unit: as on the invoice.
  scope: what the line includes (labour, parts, call-out, disposal...), in a few words.
  price: your single best estimate of t in EUR gross for the whole line, consistent with the range (inside
    [lo, hi) when both are known; near lo if hi = inf; below hi if lo = 0). If the expert paid ~0, price = 0.
  unit_rate: the rate this implies that transfers to other cases, e.g. "~EUR 75/h gross plumber",
    "~EUR 35/m3 green waste", "~EUR 900 OEM 14in MacBook display incl. fitting". Write "-" if none.
  note: max 35 words. What drives the price (OEM vs generic, standard grade, small-job minimum, how the bundle
    splits). If the range is clearly shaped by a contract rule (a % reduction, sub-limit cap, depreciation), say so
    and give the underlying item price, so the number is not misread as a market price. For ~0 lines write
    "paid 0 here (coverage), no price signal" plus a typical market price if obvious.
Be concrete, no filler."""


def fmt(lo, hi):
    return f"[{lo:g}, {'inf' if math.isinf(hi) else f'{hi:g}'})"


def one(g, effort, model="claude-opus-5-5"):
    d = HERE / "decrypted" / f"case_{g:03d}"
    rg = RANGES.get(str(g), {})
    text, imgs = case_inputs(d)
    rng = "\n".join(f"line {k}: {fmt(*v)}" for k, v in rg.items()) or "(none)"
    blocks = imgs + [{"type": "text", "text": f"{TASK}\n\n<case>\n{text}\n</case>\n\n<market_range_for_t>\n{rng}\n"
                      "</market_range_for_t>\nLines not listed had no transactions: estimate them anyway and say "
                      "'no market data' in the note."}]
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}) + "\n"
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", model, "--effort", effort, "--json-schema", json.dumps(SCHEMA),
           "--strict-mcp-config", "--no-session-persistence", "--tools", ""]
    p = subprocess.run(cmd, input=msg, capture_output=True, text=True, timeout=900, cwd="/tmp")
    ev = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    res = [e for e in ev if e.get("type") == "result"]
    if not res or res[-1].get("is_error"):
        return g, None, str(res[-1].get("result") if res else p.stderr[-300:])[:200]
    out = res[-1].get("structured_output") or json.loads(res[-1]["result"])
    OUT.mkdir(exist_ok=True)
    (OUT / f"case_{g:03d}.json").write_text(json.dumps({"game": g, "ranges": rg, **out}, indent=1, ensure_ascii=False))
    (OUT / f"case_{g:03d}.md").write_text(render(g, out, rg))
    return g, out, None


def render(g, out, rg):
    rows = [f"### Case {g}: {out['context']}"]
    for L in sorted(out["lines"], key=lambda x: x["index"]):
        r = rg.get(str(L["index"]))
        rows.append(f"- L{L['index']} {L['item']} | {L['quantity']:g} {L['unit']} | {L['scope']} | "
                    f"t~{L['price']:g} (range {fmt(*r) if r else 'n/a'}) | {L['unit_rate']} | {L['note']}")
    return "\n".join(rows) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=int); ap.add_argument("end", type=int)
    ap.add_argument("--effort", default="high"); ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", default="claude-opus-5-5")
    a = ap.parse_args()
    games = [g for g in range(a.start, a.end + 1) if (HERE / "decrypted" / f"case_{g:03d}").exists()]
    with ThreadPoolExecutor(a.jobs) as ex:
        for g, out, err in ex.map(lambda g: one(g, a.effort, a.model), games):
            print(f"case {g}: " + (f"FAILED {err}" if err else f"{len(out['lines'])} lines"), flush=True)
    book = "".join((OUT / f"case_{g:03d}.md").read_text() + "\n"
                   for g in range(0, 1000) if (OUT / f"case_{g:03d}.md").exists())
    (OUT / "PRICING_BOOK.md").write_text("# Pricing book (gross EUR, t = expert's max per whole line)\n\n" + book)
    print(f"book: ~{len(book) // 4} tokens -> {OUT / 'PRICING_BOOK.md'}")


if __name__ == "__main__":
    main()
