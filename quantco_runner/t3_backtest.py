"""Drive the session backtest through 3 visible T3 threads. NEVER submits.
usage: uv run --with pyzipper --with pillow python t3_backtest.py
"""
import json, pathlib, re, statistics, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

import session_backtest as sb

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "backtest_t3"
PROJECT = "mcp:932ac273-9e14-4728-8482-3195942818ff"
CASES = HERE / "decrypted"
B = {int(g): {int(l): tuple(v) for l, v in b.items()} for g, b in json.loads((HERE / "backtest/bounds.json").read_text()).items()}
K = max(B)  # test case = last completed game


def t3(args, stdin_text):
    p = subprocess.run(["t3", "thread", *args], input=stdin_text, capture_output=True, text=True,
                       cwd=HERE.parent / "fdn-start-hack-2026", timeout=1200)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"status": "error", "error": (p.stdout + p.stderr)[-500:], "reply": None}


def parse_lines(reply):
    if not reply: return None
    s = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", s, re.S)
    try:
        return sorted(json.loads(m.group(0))["lines"], key=lambda x: x["index"])
    except Exception:
        return None


def main():
    OUT.mkdir(exist_ok=True)
    instr = (OUT / "instructions.txt").read_text()
    threads = {}
    for name in ("A", "B", "C"):
        r = t3(["start", "--title", f"C2F session {name}", "--provider", "claudeAgent", "--model", "claude-opus-5-5",
                "--option", "effort=high", "--wait", "--json", PROJECT, "-"], instr)
        threads[name] = r.get("threadId")
        print(f"started {name}: {threads[name]} reply={r.get('reply')!r} status={r.get('status')}", flush=True)
    (OUT / "threads.json").write_text(json.dumps(threads, indent=1))
    names = list(threads)
    answers, log = {}, []

    def step(label, msgs):
        t = time.perf_counter()
        with ThreadPoolExecutor(len(names)) as ex:
            res = dict(zip(names, ex.map(lambda n: t3(["send", "--wait", "--json", threads[n], "-"], msgs[n]), names)))
        wall = time.perf_counter() - t
        (OUT / f"step_{label}.json").write_text(json.dumps(res, indent=1))
        log.append({"step": label, "wall": round(wall, 1), "status": {n: r.get("status") for n, r in res.items()}})
        print(f"[{label}] wall={wall:.1f}s status={log[-1]['status']}", flush=True)
        return res

    for g in range(0, K + 1):
        path = CASES / f"case_{g:03d}"
        res = step(f"case{g}", {n: f"CASE {g}: {path}/" for n in names})
        answers[g] = {n: parse_lines(r.get("reply")) for n, r in res.items()}
        for n, a in answers[g].items():
            if a is None: print(f"   {n}: could not parse reply: {str(res[n].get('reply') or res[n].get('error'))[:300]}", flush=True)
        if g in (0, K):
            continue
        fb = {}
        for n in names:
            rows = [sb.feedback_line(ln["index"], B[g].get(ln["index"]), ln["low"])
                    + f" (you said covered={ln['covered']}, related={ln['related']})" for ln in (answers[g][n] or [])]
            fb[n] = (f"FEEDBACK for CASE {g}:\n" + "\n".join(rows) + "\n" + sb.GOAL
                     + "\nNote what this tells you for future cases. Reply in at most 3 short sentences.")
        step(f"feedback{g}", fb)

    (OUT / "answers.json").write_text(json.dumps(answers, indent=1))
    (OUT / "log.json").write_text(json.dumps(log, indent=1))

    print("\n=== scores: thread `low` (= our charge a) vs bound, answered before feedback ===")
    for g in range(1, K + 1):
        valid = {n: a for n, a in answers[g].items() if a}
        if not valid: print(f"case {g}: no valid answers"); continue
        for i in range(max(len(a) for a in valid.values())):
            rows = {n: a[i] for n, a in valid.items() if len(a) > i}
            lows = {n: r["low"] for n, r in rows.items()}; m = statistics.median(lows.values())
            cov = sum(r["covered"] and r["related"] for r in rows.values()) * 2 > len(rows)
            hi_m = statistics.median(r["high"] for r in rows.values())
            a_, b_ = (m, m + (hi_m - m) / 3) if cov else (0.0, 0.0)
            bd = B[g].get(i + 1)
            print(f"case {g} line {i + 1}: bound {sb.fmt_bound(bd):28s} " + " ".join(f"{n}={v:.0f}" for n, v in lows.items())
                  + f"  median {m:.0f} a={a_:.0f} b={b_:.0f} -> {sb.classify(a_, bd)}")
            if g == K:
                for n, r in rows.items():
                    an = r["low"] if (r["covered"] and r["related"]) else 0.0
                    print(f"      {n}: low={r['low']:.0f} a={an:.0f} -> {sb.classify(an, bd)}")
    print(f"\nthreads: {threads}")


if __name__ == "__main__":
    main()
