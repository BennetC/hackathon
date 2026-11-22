#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Turn one past case into a compact memo: PROBLEM (only what matters) + REASONING (decision, why, lessons).

Two Opus calls, offline, never submits:
  A) blind: model sees the case only, gives coverage + fair gross total per line with reasoning.
  B) memo: model sees the case, its blind answer and the market range for t, then writes the memo.
     The memo is the ONLY thing a later model gets about this case, so PROBLEM must stand alone.

usage: uv run --script memo_writer.py <game> [--effort xhigh]
case dir = decrypted/case_{game:03d}; ranges from research/s4-imitate-404/lines.pkl (games 1-35).
"""
import argparse, base64, io, json, pathlib, pickle, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "memos"
IMG = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

RULES = """Game rules (short): for every invoice line there is a secret fair threshold t = the maximum GROSS total
(incl. VAT, whole line, not per unit) a claims expert would pay. t = 0 if the line is not covered by the policy or
not related to the reported damage. Prices on the invoice are blank; you must estimate t yourself."""

BLIND_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "covered", "fair_gross_total", "why"],
        "properties": {"index": {"type": "integer"}, "covered": {"type": "boolean"},
                       "fair_gross_total": {"type": "number"}, "why": {"type": "string"}}}}},
}
MEMO_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["problem", "decision"],
    "properties": {"problem": {"type": "string"}, "decision": {"type": "string"}},
}

MEMO_TASK = """You are writing a case memo for a library of past claims. A future model will read ~100 of these memos
INSTEAD of the original files and must learn from them how the expert decides coverage and prices. It never sees
the original policy, description, invoice or photos, only what you write.

Write two fields, plain text, dense, no filler:

problem (aim 150-400 words): the case as the future reader needs it. Peril/policy type and ONLY the clauses that
decide these lines (quote short key wording, sub-limits, deductions, exclusions). The damage facts that matter.
Every invoice line: index, description, quantity + unit, trade. What made each line tricky. Leave out addresses,
names, dates, boilerplate.

decision (aim 300-900 words): per line, the final call (covered or not; fair gross total) and the case-file facts
that justify it, then what the market range showed and how far the first estimate was from it, with the most
likely cause in the case facts or pricing. Finish with "Lessons:" - 2-6
rules that transfer to OTHER cases (how coverage clauses are read, how quantities/units/VAT/bundles/deductions
are treated, typical bias of our estimates). Lessons must be rules, not price anchors: t for the same item drifts
a lot between games and coverage of near-identical lines can flip, so never write "item X costs Y" as a lesson.
Only claim what the range actually supports; if the range is wide or one-sided, say what is still unknown.

How to read the market range [lo, hi) for t: some team charged lo and it was judged fair, so t >= lo; some team
charged hi and it was judged fraud, so t < hi. hi = inf means no charge was ever judged fraud; lo = 0 means no
positive charge was ever judged fair. A range like [0, 5] means the line was effectively not covered (t ~ 0)."""


def case_inputs(d: pathlib.Path):
    inv = next(d.glob("*.pdf"))
    invoice = subprocess.run(["pdftotext", "-layout", str(inv), "-"], capture_output=True, text=True).stdout
    text = (f"<policy>\n{(d / 'policy.txt').read_text()}\n</policy>\n"
            f"<description>\n{(d / 'description.txt').read_text()}\n</description>\n"
            f"<invoice>\n{invoice}\n</invoice>")
    blocks = []
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in IMG:
            raw, media = p.read_bytes(), IMG[p.suffix.lower()]
            if len(base64.b64encode(raw)) > 5 * 1024 * 1024:
                from PIL import Image
                im = Image.open(io.BytesIO(raw)).convert("RGB"); im.thumbnail((1568, 1568))
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=88); raw, media = buf.getvalue(), "image/jpeg"
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                       "data": base64.b64encode(raw).decode()}})
    return text, blocks


def claude(blocks, schema, effort, timeout=900):
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}) + "\n"
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", "claude-opus-5-5", "--effort", effort, "--json-schema", json.dumps(schema),
           "--strict-mcp-config", "--no-session-persistence", "--tools", ""]
    t = time.perf_counter()
    p = subprocess.run(cmd, input=msg, capture_output=True, text=True, timeout=timeout, cwd="/tmp")
    ev = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    res = [e for e in ev if e.get("type") == "result"]
    if not res or res[-1].get("is_error"):
        sys.exit(f"claude failed rc={p.returncode}: {(res[-1].get('result') if res else p.stderr[-500:])}")
    r = res[-1]
    u = r.get("usage") or {}
    print(f"  {time.perf_counter() - t:.0f}s, out_tokens={u.get('output_tokens')}", file=sys.stderr)
    return r.get("structured_output") or json.loads(r["result"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game", type=int)
    ap.add_argument("--effort", default="xhigh")
    a = ap.parse_args()

    d = HERE / "decrypted" / f"case_{a.game:03d}"
    lines, _ = pickle.load(open(HERE / "research/s4-imitate-404/lines.pkl", "rb"))
    ranges = {L["line"]: L["bound"] for L in lines if L["g"] == a.game}
    if not ranges:
        sys.exit(f"no market range for game {a.game}")
    text, imgs = case_inputs(d)

    print("A) blind answer ...", file=sys.stderr)
    blind = claude(imgs + [{"type": "text", "text": f"{RULES}\n\n<case>\n{text}\n</case>\n\nFor every invoice line "
                            "decide coverage and estimate t (fair gross total in EUR), with a one-sentence justification."}],
                   BLIND_SCHEMA, a.effort)

    OUT.mkdir(exist_ok=True)
    (OUT / f"blind_g{a.game}.json").write_text(json.dumps({"game": a.game, "ranges": ranges, "answer": blind},
                                                          indent=1, ensure_ascii=False))
    rng = "\n".join(f"line {i}: [{lo:g}, {hi:g})" for i, (lo, hi) in sorted(ranges.items()))
    print("B) memo ...", file=sys.stderr)
    memo = claude(imgs + [{"type": "text", "text": f"{MEMO_TASK}\n\n{RULES}\n\n<case>\n{text}\n</case>\n\n"
                           f"<first_estimate>\n{json.dumps(blind, indent=1, ensure_ascii=False)}\n</first_estimate>\n\n"
                           f"<market_range_for_t>\n{rng}\n</market_range_for_t>\n"
                           "Lines missing from the range list had no transactions (no information)."}],
                  MEMO_SCHEMA, a.effort)

    OUT.mkdir(exist_ok=True)
    md = f"# Case {a.game}\n\n## Problem\n\n{memo['problem']}\n\n## Decision\n\n{memo['decision']}\n"
    (OUT / f"case_{a.game:03d}.md").write_text(md)
    (OUT / f"case_{a.game:03d}.json").write_text(json.dumps({"game": a.game, "blind": blind, "ranges": ranges,
                                                              "memo": memo}, indent=1, ensure_ascii=False))
    print(md)
    print(f"~{len(md) // 4} tokens -> {OUT / f'case_{a.game:03d}.md'}", file=sys.stderr)


if __name__ == "__main__":
    main()
