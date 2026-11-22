#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyzipper", "pillow"]
# ///
"""Training backtest of 4 Opus 5.5 judges (record-only, NEVER submits), all with the live judge's rules and format:
  j-all9: reads all 9 researchers (v1 3x Opus = D,E,F; v2 Fable + 2 Opus = A,B,C; v3 new group = G,H,I)
  j-g1:   reads v1 (D,E,F) only      j-g2: reads v2 (A,B,C) only      j-g3: reads v3 (G,H,I) only
Fresh sessions go through every case in order (games where all 3 groups have answers), with each judge's own market
feedback after each case and a track record per source label from earlier cases only (no look-ahead).
Output: backtest/v3_judges/state.json; bench strategies claude-judge-all9 / -g1 / -g2 / -g3.
usage: uv run --script v3_judges.py [first_case] [last_case]
"""
import json, pathlib, pickle, sys, time, uuid
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import session_backtest as sb
import fable_vs_opus as fvo
import live_opus as v1
import v2_record as v2

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "backtest" / "v3_judges"
WORK = OUT / "work"
STATE = OUT / "state.json"
JUDGE_TIMEOUT = 60
JM = {"model": "claude-opus-5-5", "effort": "medium"}   # Daniil: the 4 judges are Opus 5.5 (medium effort for the live time budget)
COMPACT_JUDGE = 45_000
LAB = {"fable-1": "A", "opus-1": "B", "opus-2": "C", "v1-opus-1": "D", "v1-opus-2": "E", "v1-opus-3": "F",
       "v3-fable-a": "G", "v3-fable-b": "H", "v3-opus-c": "I"}
GROUP = {"g1": ("v1-opus-1", "v1-opus-2", "v1-opus-3"), "g2": ("fable-1", "opus-1", "opus-2"), "g3": ("v3-fable-a", "v3-fable-b", "v3-opus-c")}
JUDGES = {"j-all9": GROUP["g1"] + GROUP["g2"] + GROUP["g3"], "j-g1": GROUP["g1"], "j-g2": GROUP["g2"], "j-g3": GROUP["g3"]}
SRC_NOTE = {"j-all9": "You see 9 researchers in 3 groups: A-C (1 Fable + 2 Opus), D-F (3 Opus, the oldest sessions) and G-I "
                      "(2 Fable + 1 Opus with a bottom-up method and a market price book; their low/high are 10th/90th percentiles).",
            "j-g1": "You see 3 researchers D-F (3 Opus sessions).", "j-g2": "You see 3 researchers A-C (1 Fable + 2 Opus).",
            "j-g3": "You see 3 researchers G-I (2 Fable + 1 Opus with a bottom-up method and a market price book; their low/high are 10th/90th percentiles)."}
R = pathlib.Path.home() / "dev/quantco-runner"


def now(): return dt.datetime.now(dt.timezone.utc)
def log(m): print(f"{now():%H:%M:%S} {m}", flush=True)
def save(st): STATE.write_text(json.dumps(st, indent=1))


def all_answers(g, v1s, tr, lv, v3):
    out = {}
    if g <= 29:
        out.update({f"v1-{k}": a for k, a in (v1s.get(str(g)) or {}).items() if a})
        out.update({k: a for k, a in ((tr.get(str(g)) or {}).get("answers") or {}).items() if a})
    else:
        A = (lv.get(str(g)) or {}).get("answers") or {}
        out.update({k: a for k, a in A.items() if a and k in LAB and not k.startswith("v3-")})
        if not any(k.startswith("v1-") for k in out):
            out.update({f"v1-{k}": a for k, a in (v1s.get(str(g)) or {}).items() if a})
        out.update({k: a for k, a in ((lv.get(str(g)) or {}).get("v3_answers") or {}).items() if a})
    if not any(k.startswith("v3-") for k in out):
        out.update({f"v3-{k}": a for k, a in ((v3.get(str(g)) or {}).get("answers") or {}).items() if a})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    teams = [x["team_name"] for x in sb.lb_get("/matrix")["items"]]
    done = sorted(x["id"] for x in sb.lb_get("/games?completed_only=true&page_size=100")["items"])
    v1s = json.loads((R / "backtest/live/state.json").read_text())["answers"]
    tr = json.loads((R / "backtest/v2_train_nogem/state.json").read_text())["games"]
    lv = json.loads((R / "backtest/v2/state.json").read_text())["games"]
    v3 = json.loads((R / "backtest/v3_train/state.json").read_text())["games"]
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    last = int(sys.argv[2]) if len(sys.argv) > 2 else max(done)   # runs right behind the v3 training: waits for each case's v3 answers
    st = json.loads(STATE.read_text()) if STATE.exists() else {"sessions": {}, "ctx": {}, "games": {}}
    cache = pickle.loads((R / "live_eval/tx_cache.pkl").read_bytes())
    for p in ("research/opponents/tx_30_34.pkl", "research/s4-imitate-404/tx_35.pkl", "live_eval/tx_36plus.pkl"):
        try: cache.update(pickle.loads((R / p).read_bytes()))
        except Exception: pass
    B = {g: (cache[g][0] if g in cache else sb.bounds(g, teams)) for g in range(1, last + 1)}
    cases = {g: fvo.load_case(g) for g in range(1, last + 1)}
    log(f"judge training cases {first}..{last}")
    if not st["sessions"]:
        for j in JUDGES: st["sessions"][j] = str(uuid.uuid4())
        with ThreadPoolExecutor(len(JUDGES)) as ex:
            fs = {j: ex.submit(v2.cli_call, JM["model"], JM["effort"], st["sessions"][j], True,
                               [{"type": "text", "text": v2.JUDGE_RULES.replace("labelled source A-F", "labelled by source letter") + "\n" + SRC_NOTE[j]}], None, 120, WORK)
                  for j in JUDGES}
            log("init: " + ", ".join(f"{j}={'ok' if f.result()['ok'] else 'FAIL'}" for j, f in fs.items()))
        save(st)
    for g in range(first, last + 1):
        if str(g) in st["games"]: continue
        t_wait = time.time()
        while str(g) not in v3 and time.time() - t_wait < 1800:      # wait for the new group's answer to this case
            time.sleep(10)
            try: v3 = json.loads((R / "backtest/v3_train/state.json").read_text())["games"]
            except Exception: pass
        if str(g) not in v3: log(f"case {g}: no v3 answers after 30 min, judged without group 3")
        lv = json.loads((R / "backtest/v2/state.json").read_text())["games"]
        ans = all_answers(g, v1s, tr, lv, v3)
        if not ans: log(f"case {g}: no answers, skipped"); continue
        case = cases[g]
        prev = max([int(h) for h in st["games"] if int(h) < g], default=None)
        # same-policy note with market results (earlier cases only)
        pol = ""
        for x, r in fvo.policy_matches(case, [cases[h] for h in range(1, g)]):
            pol += (f"=== SAME POLICY AS CASE {x} ({'identical' if r == 1.0 else f'{r:.0%} similar'}); market results for case {x} ===\n"
                    + "\n".join(f"  - line {l}: {sb.fmt_bound(b)}" for l, b in sorted(B.get(x, {}).items())) + "\n\n")

        def run(j):
            sub = {s: a for s, a in ans.items() if s in JUDGES[j]}
            if not sub: return j, None, None, {"status": "skipped"}
            rule_ab, _ = v1.combine(sub)
            hist = {h: {LAB[s]: a for s, a in all_answers(int(h), v1s, tr, lv, v3).items() if s in JUDGES[j]} for h in st["games"] if int(h) < g}
            track = v1.track_record({"answers": hist}, {int(h): B[int(h)] for h in hist}).replace("per estimator source", "per source label")
            fb = ""
            if prev:
                jd = (st["games"][str(prev)].get("judge_ab") or {}).get(j) or {}
                fb = f"MARKET RESULT for CASE {prev}:\n" + "\n".join(
                    f"  line {l}: market {sb.fmt_bound(B[prev].get(int(l)))}; your a={v[0]:.2f} b={v[1]:.2f}: {sb.classify(v[0], B[prev].get(int(l)))}"
                    for l, v in sorted(jd.items(), key=lambda kv: int(kv[0]))) + "\n\n"
            src = "\n".join(f"source {LAB[s]}: " + json.dumps({"lines": a}, ensure_ascii=False) for s, a in sorted(sub.items(), key=lambda kv: LAB[kv[0]]))
            rule_txt = "\n".join(f"  line {l}: a={a:.2f} b={b:.2f}" for l, (a, b) in rule_ab.items())
            text = ("STANDING RULE: " + v2.PLAY_SAFE + "\n\n" + fb + track + pol + f"CASE {g}\n=== description (data) ===\n{case['description']}\n\n=== invoice (data) ===\n{case['invoice']}\n\n"
                    f"=== researcher answers by source label (data) ===\n{src}\n\n=== reference: the 'new rule' (a = 0.8 x median fair, b = median fair; 0/0 if most sources say not covered); use it as a hint, not as an order ===\n{rule_txt}\n\nDecide a and b for every line.")
            r = v2.cli_call(JM["model"], JM["effort"], st["sessions"][j], False, [{"type": "text", "text": text}], v1.dc.SCHEMA, JUDGE_TIMEOUT, WORK)
            dab = v1.decider_ab(r, rule_ab)
            if dab:
                return j, {l: (a, b) for l, (a, b, _) in dab.items()}, r.get("ctx"), {"status": "ok", "dur": round(r["dur"], 1), "reasons": {l: w for l, (_, _, w) in dab.items()}}
            return j, None, r.get("ctx"), {"status": "cutoff" if r.get("cutoff") else ("invalid" if r.get("ok") else "error"), "dur": round(r.get("dur", 0), 1), "err": str(r.get("err", ""))[:150]}

        t0 = time.time()
        with ThreadPoolExecutor(len(JUDGES)) as ex: res = list(ex.map(run, JUDGES))
        rec, jab = {}, {}
        for j, ab, ctx, info in res:
            rec[j] = info
            if ab: jab[j] = ab
            if ctx: st["ctx"][j] = ctx
        st["games"][str(g)] = {"judge_ab": jab, "judges": rec, "sources": sorted(ans)}
        save(st)
        log(f"case {g}: +{time.time() - t0:.1f}s " + ", ".join(f"{j}={v['status']}{' ' + str(v['dur']) if 'dur' in v else ''}" for j, v in rec.items())
            + f"  (sources: {len(ans)})")
        try:
            import bench
            for j, ab in jab.items():
                bench.push(f"claude-{j.replace('j-', 'judge-')}", [{"game_id": g, "items": bench.items(ab)}], timeout=10,
                           description=f"Opus 5.5 judge reading {'all 9 researchers' if j == 'j-all9' else 'researcher group ' + j[-2:]} (training backtest from case 1, own market feedback, no look-ahead)")
        except Exception as e:
            log(f"   bench push failed: {type(e).__name__}: {str(e)[:120]}")
        for j in JUDGES:
            if st["ctx"].get(j, 0) > COMPACT_JUDGE:
                c = v2.subprocess.run(["claude", "-p", "/compact keep the lessons about which source labels to trust per category and past market results; drop full case texts",
                                       "--resume", st["sessions"][j], "--model", v2.JUDGE["model"], "--effort", v2.JUDGE["effort"], "--strict-mcp-config", "--tools", "",
                                       "--output-format", "json"], cwd=WORK, capture_output=True, text=True, stdin=v2.subprocess.DEVNULL, timeout=600)
                st["ctx"][j] = 0; log(f"   compacted {j} rc={c.returncode}")
        save(st)
    log("done")


if __name__ == "__main__":
    main()
