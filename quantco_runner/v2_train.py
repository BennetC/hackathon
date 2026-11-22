#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyzipper", "pillow"]
# ///
"""Full training backtest of the v2 setup. NEVER submits.

Fresh sessions: 1 Fable 5.2 (medium), 2 Opus 5.5 (high), 3 Gemini 4 Neon (low, via agy) + 1 Fable judge (medium).
They go through every completed case from 1, in order, with the market feedback after each case.

No look-ahead: everything learned from the game is built only from cases BEFORE the current one, from this run's own
answers: calibration table, per-source track record, 'same policy as case X' note, feedback. The fact-checked
CORRECTION / g21 texts are NOT used (they were written from the results of cases 1-21). The Munich price reference is
external real-world data (web research), so it is included from the start.

Researchers: 30 s cutoff each, 'too slow' note next time. Gemini sees the photo via its file tool (a dir with only the
photo); Fable/Opus get it inline. Pauses around live release windows. Output: backtest/v2_train/.
usage: uv run --script v2_train.py [first_case] [last_case]
"""
import collections, json, pathlib, shutil, statistics, sys, tempfile, time, urllib.error, uuid
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import opus_case as oc
import session_backtest as sb
import fable_vs_opus as fvo
import live_opus as v1
import v2_record as v2
import openai_judge as oj   # 2nd judge: OpenAI GPT-6.2 Astra (Responses API, persistent via previous_response_id)

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "backtest" / "v2_train_nogem"   # run without Gemini (the run with Gemini is in backtest/v2_train)
v2.WORK = OUT / "work"                     # Claude sessions of this run live here (--resume needs the same cwd)
STATE = OUT / "state.json"
LABELS = {"fable-1": "A", "opus-1": "B", "opus-2": "C"}
RESEARCHERS = [r for r in v2.RESEARCHERS if r["kind"] == "cli"]   # Fable + 2 Opus (Gemini removed)
DEADLINE = 30
JUDGE_TIMEOUT = 60
COMPACT_RESEARCHER, COMPACT_JUDGE = 120_000, 45_000

MUNICH = """=== MUNICH PRICE REFERENCE (external web research, gross incl. 19% VAT unless noted) ===
- Plumber 89-107 EUR/h, senior plumber about 114 EUR/h; joiner 77 (journeyman) to 113 (master) EUR/h; electrician 70-115 EUR/h (VAT unclear).
- Call-out in the city 50-80 EUR per visit. Bicycle workshop 89-108 EUR/h (German average 85). Laptop diagnosis 20-80 EUR.
- German average selling prices incl. VAT (2025 market index): TV 642, speakers incl. soundbars 319, hi-fi components 456.
- No reliable Munich figure found for glazier, painter, clearance per m3 or thermal imaging: estimate those yourself.

"""


def now(): return dt.datetime.now(dt.timezone.utc)
def log(m): print(f"{now():%H:%M:%S} {m}", flush=True)
def save(st): STATE.write_text(json.dumps(st, indent=1))


def wait_outside_live_windows(starts):
    """Start a case only if no live release is within the next 90 s or the last 70 s (a case takes up to ~60 s)."""
    return   # Daniil: training and the live runs may run at the same time (no pause around releases)


def agy_photo(model, conv, text, photo_path, timeout):
    """Gemini via agy with the photo as the only file in its own empty working dir (opened with its file tool).
    Each call has its own dir and its own cwd (no shared globals), so the 3 Gemini calls can run in parallel."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="trainagy."))
    try:
        if photo_path:
            shutil.copy(photo_path, d / photo_path.name)
            text = (f"The claim photo is ./{photo_path.name} in the current directory. Look at that one image with your file viewing tool, "
                    "once. Do not use any other tool, do not run commands, do not write files.\n\n" + text)
        cmd = [v2.AGY, "--model", model, "--output-format", "stream-json", "--print-timeout", f"{max(1, int(timeout))}s",
               "--json-schema", json.dumps(oc.SCHEMA), *(["--conversation", conv] if conv else []), "-p", text]
        t = time.perf_counter()
        try:
            p = v2.subprocess.run(cmd, cwd=d, capture_output=True, text=True, stdin=v2.subprocess.DEVNULL, timeout=max(2, timeout + 2))
        except v2.subprocess.TimeoutExpired:
            return {"ok": False, "cutoff": True, "dur": time.perf_counter() - t, "err": f"cut off after {timeout:.0f}s"}
        dur = time.perf_counter() - t
        ev = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
        res = next((e["result"] for e in ev if e.get("event") == "result"), {})
        if res.get("status") != "SUCCESS":
            cut = "timeout" in (p.stderr + str(res.get("error", ""))).lower() or p.returncode == 3
            return {"ok": False, "cutoff": cut, "dur": dur, "err": (res.get("error") or p.stderr[-200:])[:200]}
        return {"ok": True, "cutoff": False, "dur": dur, "structured": res.get("structured_output")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def calibration(st, B, upto):
    err = collections.defaultdict(list)
    for h in range(1, upto):
        ans = [a for a in (st["games"].get(str(h), {}).get("answers") or {}).values() if a]
        if not ans or h not in B: continue
        for i in range(max(len(a) for a in ans)):
            rows = [a[i] for a in ans if len(a) > i]
            lo, _ = sb._sides(B[h].get(i + 1))
            if not lo or sum(bool(r["covered"] and r["related"]) for r in rows) * 2 <= len(rows): continue
            err[v1.category(rows[0].get("description", ""))].append((statistics.median(r["low"] for r in rows) - lo) / lo * 100)
    if not err: return ""
    return ("=== CALIBRATION (from the cases so far; negative = our lows were below the market's safe charge) ===\n"
            + "\n".join(f"- {c}: lows typically {statistics.median(e):+.0f}% vs the safe charge (n={len(e)})" for c, e in sorted(err.items(), key=lambda kv: -len(kv[1])))
            + "\n\n")


def policy_note(case, cases, st, B, upto):
    out = ""
    for x, r in fvo.policy_matches(case, [cases[h] for h in range(1, upto) if h in cases]):
        any_ans = next((a for a in (st["games"].get(str(x), {}).get("answers") or {}).values() if a), [])
        rows = [f"  - line {ln['index']} ({ln['description'][:80]}): {sb.fmt_bound(B.get(x, {}).get(ln['index']))}" for ln in any_ans]
        out += (f"=== SAME POLICY AS CASE {x} ({'identical' if r == 1.0 else f'{r:.0%} similar'}); market results for case {x} ===\n"
                + "\n".join(rows) + "\n\n")
    return out


def old_rule(answers):
    """Pre-patch rule: a = median low, b = a + (median high - a)/3 on majority covered+related lines."""
    valid = [a for a in answers.values() if a]; out = {}
    if not valid: return out
    for i in range(max(len(a) for a in valid)):
        rows = [a[i] for a in valid if len(a) > i]
        cov = sum(bool(r["covered"] and r["related"]) for r in rows) * 2 > len(rows)
        lo_ = statistics.median(r["low"] for r in rows); hi_ = statistics.median(r["high"] for r in rows)
        out[i + 1] = (round(lo_, 2), round(lo_ + (hi_ - lo_) / 3, 2)) if cov else (0.0, 0.0)
    return out


def new_rule(answers):
    """Research fallback: a = 0.8 x median fair, b = median fair on majority-covered lines; else 0/0."""
    valid = [a for a in answers.values() if a]; out = {}
    if not valid: return out
    for i in range(max(len(a) for a in valid)):
        rows = [a[i] for a in valid if len(a) > i]
        cov = sum(bool(r["covered"] and r["related"]) for r in rows) * 2 > len(rows)
        f = statistics.median(r["fair_gross_total"] for r in rows)
        out[i + 1] = (round(0.8 * f, 2), round(f, 2)) if cov else (0.0, 0.0)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True); v2.WORK.mkdir(parents=True, exist_ok=True)
    teams = [x["team_name"] for x in sb.lb_get("/matrix")["items"]]
    done = sorted(x["id"] for x in sb.lb_get("/games?completed_only=true&page_size=100")["items"])
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    last = int(sys.argv[2]) if len(sys.argv) > 2 else max(done)
    games = json.loads(urllib.request.urlopen(urllib.request.Request(oc.BASE + "/api/games/list", headers={"X-API-Key": oc.api_key()}), timeout=10).read())
    starts = [dt.datetime.fromisoformat(g["start_time"].replace("Z", "+00:00")).timestamp() for g in games]
    st = json.loads(STATE.read_text()) if STATE.exists() else {"sessions": {}, "judge": None, "late": {}, "ctx": {}, "games": {}}
    log(f"training cases {first}..{last} (completed: {done[-1]})")
    B = {g: sb.bounds(g, teams) for g in range(1, last + 1)}
    cases = {g: fvo.load_case(g) for g in range(1, last + 1)}
    photos = {}
    for g in range(1, last + 1):                       # decrypt once to get the photo files for Gemini
        d = OUT / "photos" / f"case_{g:03d}"
        if not d.exists():
            d.mkdir(parents=True); k = oc.fetch_key(g); tmp = pathlib.Path(tempfile.mkdtemp())
            oc.decrypt(oc.find_zip(g), k, tmp); del k
            for p in tmp.rglob("*"):
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"): shutil.copy(p, d / p.name)
            shutil.rmtree(tmp, ignore_errors=True)
        photos[g] = next(iter(sorted(d.iterdir())), None)

    standing = v2.RESEARCH_RULES.replace("Reply to this message with just: ok", "") + "\n" + MUNICH + "Reply to this message with just: ok"
    judge_rules = v2.JUDGE_RULES
    if not st["sessions"]:
        cli = [r for r in RESEARCHERS if r["kind"] == "cli"]; agy = [r for r in RESEARCHERS if r["kind"] == "agy"]
        for r in cli: st["sessions"][r["slot"]] = str(uuid.uuid4())
        st["judge"] = str(uuid.uuid4())
        with ThreadPoolExecutor(8) as ex:
            fc = {r["slot"]: ex.submit(v2.cli_call, r["model"], r["effort"], st["sessions"][r["slot"]], True, [{"type": "text", "text": standing}], None, 120) for r in cli}
            fa = {r["slot"]: ex.submit(v2.agy_call, r["model"], None, standing, None, 120) for r in agy}
            fj = ex.submit(v2.cli_call, v2.JUDGE["model"], v2.JUDGE["effort"], st["judge"], True, [{"type": "text", "text": judge_rules}], None, 120)
            for slot, f in fa.items(): st["sessions"][slot] = f.result().get("conv")
            ai = oj.call(judge_rules, None, None, 120); st["astra"] = ai.get("id") if ai.get("ok") else None
            log(f"astra judge init ok={ai.get('ok')} {ai.get('err', '')}")
            log("init: " + ", ".join(f"{k}={'ok' if v.result()['ok'] else 'FAIL'}" for k, v in {**fc, **fa}.items()) + f"; judge={fj.result()['ok']}")
        save(st)

    for g in range(first, last + 1):
        if str(g) in st["games"]: continue
        wait_outside_live_windows(starts)
        case = cases[g]; prev = g - 1 if g > 1 else None
        shared = calibration(st, B, g) + MUNICH + policy_note(case, cases, st, B, g)
        case_text = f"CASE {g}\n\n" + oc.build_prompt(case["policy"], case["description"], case["invoice"], case["imgs"])
        fb = {}
        if prev and str(prev) in st["games"]:
            for slot, a in (st["games"][str(prev)].get("answers") or {}).items():
                fb[slot] = f"MARKET RESULT for CASE {prev}:\n" + "\n".join(
                    f"  line {ln['index']}: market {sb.fmt_bound(B[prev].get(ln['index']))}; your low was {ln['low']:.2f}: {sb.classify(ln['low'], B[prev].get(ln['index']))}"
                    for ln in a) + "\n\n"
            for slot in st["games"][str(prev)].get("researchers", {}):
                if slot not in fb and slot in st["sessions"]:
                    fb[slot] = (f"MARKET RESULT for CASE {prev} (you had no valid answer):\n" + "\n".join(
                        f"  line {l}: market {sb.fmt_bound(b)}" for l, b in sorted(B[prev].items())) + "\n\n")

        def run(r):
            note = v2.LATE_NOTE if st["late"].get(r["slot"]) else ""
            if r["kind"] == "cli":
                return r["slot"], v2.cli_call(r["model"], r["effort"], st["sessions"][r["slot"]], False,
                                              case["image_blocks"] + [{"type": "text", "text": note + fb.get(r["slot"], "") + shared + case_text}], oc.SCHEMA, DEADLINE)
            if not st["sessions"].get(r["slot"]): return r["slot"], {"ok": False, "skipped": True, "dur": 0.0}
            return r["slot"], agy_photo(r["model"], st["sessions"][r["slot"]], note + v2.RULE30 + "\n\n" + fb.get(r["slot"], "") + shared + case_text,
                                        photos.get(g), DEADLINE - 0.5)

        t0 = time.time()
        with ThreadPoolExecutor(len(RESEARCHERS)) as ex: res = dict(ex.map(run, RESEARCHERS))
        t_res = time.time() - t0
        answers, rec = {}, {}
        for slot, r in res.items():
            if r.get("ok") and r.get("structured"):
                answers[slot] = sorted(r["structured"]["lines"], key=lambda x: x["index"]); st["late"][slot] = False
                if r.get("ctx"): st["ctx"][slot] = r["ctx"]
                rec[slot] = {"status": "ok", "dur": round(r["dur"], 1)}
            else:
                st["late"][slot] = bool(r.get("cutoff")); rec[slot] = {"status": "cutoff" if r.get("cutoff") else ("skipped" if r.get("skipped") else "error"),
                                                                       "dur": round(r.get("dur", 0), 1), "err": str(r.get("err", ""))[:150]}
        rule_old = old_rule(answers); rule_new = new_rule(answers)
        # judge
        lab_st = {"answers": {h: {LABELS[s]: a for s, a in v["answers"].items() if a} for h, v in st["games"].items()}}
        track = v1.track_record(lab_st, {h: B[h] for h in range(1, g)}).replace("per estimator source", "per source label")
        jfb = ""
        if prev and str(prev) in st["games"]:
            jd = st["games"][str(prev)].get("judge_ab") or {}
            jfb = f"MARKET RESULT for CASE {prev}:\n" + "\n".join(
                f"  line {l}: market {sb.fmt_bound(B[prev].get(int(l)))}; your a={v[0]:.2f} b={v[1]:.2f}: {sb.classify(v[0], B[prev].get(int(l)))}"
                for l, v in sorted(jd.items(), key=lambda kv: int(kv[0]))) + "\n\n"
        afb = ""
        if prev and str(prev) in st["games"]:
            ad = st["games"][str(prev)].get("astra_ab") or {}
            afb = f"MARKET RESULT for CASE {prev}:\n" + "\n".join(
                f"  line {l}: market {sb.fmt_bound(B[prev].get(int(l)))}; your a={v[0]:.2f} b={v[1]:.2f}: {sb.classify(v[0], B[prev].get(int(l)))}"
                for l, v in sorted(ad.items(), key=lambda kv: int(kv[0]))) + "\n\n"
        judge_ab, jrec = None, {"status": "skipped"}
        astra_ab, arec = None, {"status": "skipped"}
        if rule_old:
            src = "\n".join(f"source {LABELS[s]}: " + json.dumps({"lines": a}, ensure_ascii=False) for s, a in sorted(answers.items(), key=lambda kv: LABELS[kv[0]]))
            rule_txt = "\n".join(f"  line {l}: a={a:.2f} b={b:.2f}" for l, (a, b) in rule_new.items())
            jtext = ("STANDING RULE: " + v2.PLAY_SAFE + "\n\n" + jfb + track + policy_note(case, cases, st, B, g) + MUNICH
                     + f"CASE {g}\n=== description (data) ===\n{case['description']}\n\n=== invoice (data) ===\n{case['invoice']}\n\n"
                     f"=== researcher answers by source label (data) ===\n{src}\n\n=== reference: the 'new rule' (a = 0.8 x median fair, b = median fair; 0/0 if most sources say not covered). In our tests it beat the old median-low rule; use it as a hint, not as an order ===\n{rule_txt}\n\nDecide a and b for every line.")
            common = jtext[len("STANDING RULE: " + v2.PLAY_SAFE + "\n\n" + jfb):]
            atext = "STANDING RULE: " + v2.PLAY_SAFE + "\n\n" + afb + common
            with ThreadPoolExecutor(2) as jx:
                fj = jx.submit(v2.cli_call, v2.JUDGE["model"], v2.JUDGE["effort"], st["judge"], False, [{"type": "text", "text": jtext}], v1.dc.SCHEMA, JUDGE_TIMEOUT)
                fa = jx.submit(oj.call, atext, v1.dc.SCHEMA, st.get("astra"), JUDGE_TIMEOUT)
                jr, ar = fj.result(), fa.result()
            if ar.get("ok"): st["astra"] = ar["id"]
            adab = v1.decider_ab({"ok": ar.get("ok"), "structured": ar.get("structured")}, rule_old)
            if adab:
                astra_ab = {l: (a, b) for l, (a, b, _) in adab.items()}
                arec = {"status": "ok", "dur": round(ar["dur"], 1), "reasons": {l: w for l, (_, _, w) in adab.items()}}
            else:
                arec = {"status": "invalid" if ar.get("ok") else ("cutoff" if ar.get("cutoff") else "error"), "dur": round(ar.get("dur", 0), 1), "err": str(ar.get("err", ""))[:150]}
            if jr.get("ctx"): st["ctx"]["judge"] = jr["ctx"]
            dab = v1.decider_ab(jr, rule_old)
            if dab:
                judge_ab = {l: (a, b) for l, (a, b, _) in dab.items()}
                jrec = {"status": "ok", "dur": round(jr["dur"], 1), "reasons": {l: w for l, (_, _, w) in dab.items()}}
            else:
                jrec = {"status": "cutoff" if jr.get("cutoff") else ("invalid" if jr.get("ok") else "error"), "dur": round(jr.get("dur", 0), 1), "err": str(jr.get("err", ""))[:150]}
        st["games"][str(g)] = {"answers": answers, "researchers": rec, "judge": jrec, "judge_ab": judge_ab, "astra": arec, "astra_ab": astra_ab,
                               "rule_old_ab": rule_old, "rule_new_ab": rule_new, "t_research": round(t_res, 1)}
        save(st)
        log(f"case {g}: researchers +{t_res:.1f}s [" + ", ".join(f"{LABELS[s]}={v['status']}{'' if v['status'] == 'skipped' else ' ' + str(v['dur'])}" for s, v in rec.items())
            + f"] fable judge {jrec['status']} {jrec.get('dur', '')}s, astra judge {arec['status']} {arec.get('dur', '')}s")
        # bench (backtest strategies)
        try:
            import bench
            for name, ab in (("claude-v2train-nogem-judge", judge_ab), ("claude-v2train-nogem-astra-judge", astra_ab), ("claude-v2train-nogem-rule-new", rule_new), ("claude-v2train-nogem-rule-old", rule_old)):
                if ab: bench.push(name, [{"game_id": g, "items": bench.items(ab)}], timeout=10,
                                  description="v2 training without Gemini (Fable + 2 Opus + Fable judge with new-rule hint; fresh sessions, no look-ahead)")
        except Exception as e:
            log(f"   bench push failed: {type(e).__name__}: {str(e)[:120]}")
        # compaction between cases (Claude sessions; Gemini manages its own context)
        for r in RESEARCHERS:
            if r["kind"] == "cli" and st["ctx"].get(r["slot"], 0) > COMPACT_RESEARCHER:
                c = v2.subprocess.run(["claude", "-p", "/compact keep the market lessons and each past case's line prices and market results; drop full case texts",
                                       "--resume", st["sessions"][r["slot"]], "--model", r["model"], "--effort", r["effort"], "--strict-mcp-config", "--tools", "",
                                       "--output-format", "json"], cwd=v2.WORK, capture_output=True, text=True, stdin=v2.subprocess.DEVNULL, timeout=600)
                st["ctx"][r["slot"]] = 0; log(f"   compacted {r['slot']} rc={c.returncode}")
        if st["ctx"].get("judge", 0) > COMPACT_JUDGE:
            c = v2.subprocess.run(["claude", "-p", "/compact keep the lessons about which source labels to trust per category and past market results; drop full case texts",
                                   "--resume", st["judge"], "--model", v2.JUDGE["model"], "--effort", v2.JUDGE["effort"], "--strict-mcp-config", "--tools", "",
                                   "--output-format", "json"], cwd=v2.WORK, capture_output=True, text=True, stdin=v2.subprocess.DEVNULL, timeout=600)
            st["ctx"]["judge"] = 0; log(f"   compacted judge rc={c.returncode}")
        save(st)

    # ---------------- report ----------------
    live = json.loads((HERE / "backtest/live/state.json").read_text())
    T = collections.defaultdict(lambda: [0.0, 0.0]); print("\ncase | judge | new rule 0.8F/F | old rule | FDN actual")
    for g in range(first, last + 1):
        G = st["games"].get(str(g))
        if not G: continue
        tx = fvo.tx_all(g, teams); row = []
        for k in ("judge_ab", "rule_new_ab", "rule_old_ab"):
            ab = {int(l): tuple(v) for l, v in (G.get(k) or {}).items()}
            if not ab: row.append("n/a"); continue
            r = fvo.replay(g, ab, tx, teams, B[g]); T[k][0] += r["net_lo"]; T[k][1] += r["net_hi"]; act = r["actual"]
            row.append(f"{r['net_lo']:+.0f}..{r['net_hi']:+.0f}")
        T["actual"][0] += act; T["actual"][1] += act
        print(f"{g:>4} | " + " | ".join(row) + f" | {act:+.0f}")
    print(" all | " + " | ".join(f"{T[k][0]:+.0f}..{T[k][1]:+.0f}" for k in ("judge_ab", "rule_new_ab", "rule_old_ab", "actual")))


if __name__ == "__main__":
    main()
