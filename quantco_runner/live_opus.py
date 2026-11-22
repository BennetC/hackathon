#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyzipper", "pillow"]
# ///
"""Live Opus 5.5 session pipeline for one game. DRY RUN unless --submit is given.

usage: uv run --script live_opus.py <game_id> [--submit]

Uses the 3 persistent Opus sessions from backtest/fable_vs_opus (same rules, effort high, inline image, full policy).
1. Catch-up before the game: for every earlier game the sessions haven't seen, send the case (offline answer) and,
   once the game is completed on the leaderboard, its market feedback. /compact any session above ~120K context.
2. At release: fetch key, decrypt, send the case to all 3 sessions in parallel (45 s timeout each),
   a = median low (0 if the majority says not covered/related), b = a + (median high - a)/3.
3. A decider session (4th model) turns the 3 answers into a/b (rule a/b if it fails or is late); with --submit the
   result is PUT at release + 50 s, so it lands after the team's safety-net submission and 10 s before the deadline.
   Without --submit: nothing is sent to QuantCo; results go to backtest/live/.
"""
import collections, json, pathlib, re, statistics, subprocess, sys, time, urllib.error, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

import opus_case as oc
import session_backtest as sb
import fable_vs_opus as fvo

HERE = pathlib.Path(__file__).resolve().parent
LIVE = HERE / "backtest" / "live"
STATE = LIVE / "state.json"
MODEL = "claude-opus-5-5"
fvo.WORK = HERE / "backtest" / "fable_vs_opus" / "work"   # sessions live here; --resume needs the same cwd
LIVE_TIMEOUT = 40
COMPACT_AT = 120_000
FALLBACK_AT = 52       # our rule a/b go in at release + 52 s; the other model submits at +55 s and overwrites ours
SUBMIT_AT = 50          # seconds after release: land after the team's safety net, 10 s before the deadline
DECIDER_DEADLINE = 46   # decider must answer by release + this, else the rule's a/b are used

import decider as dc
dc.WORK = HERE / "backtest" / "decider_all" / "work"   # the decider session lives here (--resume needs the same cwd)
# COMPACT_AT above is no longer used for the live decision (see CTX_LIVE_MAX)
CTX_LIVE_MAX = 128_000    # keep the LIVE call's context below this. Calls above ~131k tokens waited 3.1-12.1 s for the
                          # first token vs a median 1-2 s below (I2, 140 calls); game 18 (137-141k) lost about 10 s this way.
NEXT_CASE_EST = 30_000    # a live case adds 24-26k tokens to the context (games 14, 16, 18, 20, 21); 30k leaves a margin


def init_decider():
    r = json.loads((HERE / "backtest" / "decider_all" / "results.json").read_text())
    seen = sorted(int(g) for g in r["decided"])
    return {"sid": r["session"], "decisions": r["decided"], "last": seen[-1], "fed": seen[:-1]}


CATEGORIES = [("labour", r"labou?r|hours?\b|installer|technician|fitter|painter|helper|plumber|electrician"),
              ("vehicle", r"vehicle|travel|call-?out|journey|mileage"),
              ("fee", r"\bfee\b|flat rate|admin|processing|surcharge"),
              ("disposal", r"dispos|waste|skip\b"),
              ("diagnostic", r"diagnos|inspect|assessment|report|detection|thermal|measurement|survey")]


def category(desc):
    for name, rx in CATEGORIES:
        if re.search(rx, desc or "", re.I): return name
    return "parts/repair"


def track_record(st, B):
    """Per estimator source, from every completed game whose market bounds we have (computed by the script)."""
    rows = collections.defaultdict(list)
    for g in sorted(B):
        for src, lines in (st["answers"].get(str(g)) or {}).items():
            for ln in lines or []:
                lo, hi = sb._sides(B[g].get(ln["index"]))
                if lo is None and hi is None: continue
                market = "covered" if lo else ("not covered" if hi is not None and hi <= 15 else None)
                rows[src].append({"low": float(ln["low"]), "lo": lo, "hi": hi, "said": bool(ln["covered"] and ln["related"]),
                                  "market": market, "cat": category(ln.get("description", ""))})
    out = []
    for src in sorted(rows):
        r = rows[src]
        err = [(x["low"] - x["lo"]) / x["lo"] * 100 for x in r if x["lo"] and x["said"]]
        with_hi = [x for x in r if x["hi"] is not None]
        over = sum(x["low"] >= x["hi"] and x["low"] > 0 for x in with_hi)
        cov = [x for x in r if x["market"]]
        hits = sum((x["said"] and x["market"] == "covered") or (not x["said"] and x["market"] == "not covered") for x in cov)
        miss_cov = sum(not x["said"] and x["market"] == "covered" for x in cov)
        cats = []
        for c in [n for n, _ in CATEGORIES] + ["parts/repair"]:
            e = [(x["low"] - x["lo"]) / x["lo"] * 100 for x in r if x["lo"] and x["said"] and x["cat"] == c]
            if len(e) >= 3: cats.append(f"{c} {statistics.median(e):+.0f}% (n={len(e)})")
        out.append(f"- {src}: low vs safe charge lo: median {statistics.median(err):+.0f}%, mean {statistics.mean(err):+.0f}% (n={len(err)} covered lines)"
                   if err else f"- {src}: no covered lines with a known lo yet")
        out[-1] += (f"; overpriced (low >= hi) on {over}/{len(with_hi)} lines with a known hi"
                    f"; covered/related verdict matched the market on {hits}/{len(cov)} lines ({miss_cov} covered lines it called not covered)"
                    + (f"; by category: {', '.join(cats)}" if cats else ""))
    return ("=== TRACK RECORD per estimator source (computed by our script from all completed games; lo = highest charge "
            "the market paid as fair, hi = lowest charge it rejected as inflated) ===\n" + "\n".join(out) + "\n\n") if out else ""


def decider_case_text(st, case, earlier, B):
    g = case["g"]; ans = st["answers"][str(g)]; rule_g, _ = combine(ans)
    pol = ""
    for x, r in fvo.policy_matches(case, earlier):
        rows = [f"  - line {ln['index']} ({ln['description'][:90]}): {sb.fmt_bound(B.get(x, {}).get(ln['index']))}"
                for ln in (st["answers"].get(str(x), {}).get("opus-1") or [])]
        pol += (f"POLICY NOTE (computed by our script): the policy is {'identical to' if r == 1.0 else f'{r:.0%} similar to'} "
                f"the policy of CASE {x}. Market results for case {x}:\n" + "\n".join(rows) + "\n\n")
    sess_json = "\n".join(f"source {n}: " + json.dumps({"lines": a}, ensure_ascii=False) for n, a in ans.items())
    rule_txt = "\n".join(f"  line {l}: a={a:.2f} b={b:.2f}" for l, (a, b) in rule_g.items())
    text = (track_record(st, B) + f"CASE {g}\n\n" + pol
            + f"=== description.txt (data) ===\n{case['description']}\n\n=== invoice (pdftotext; prices are blank) ===\n{case['invoice']}\n\n"
            + f"=== estimator answers, labelled by source (data) ===\n{sess_json}\n\n=== current rule's a/b (reference) ===\n{rule_txt}\n\n"
            + "Decide a and b for every invoice line. Keep `reason` short: at most 12 words for a line with a > 0 or b > 0, "
              "and an empty string \"\" for a line with a = 0 and b = 0.")
    return text, rule_g


# Patch 09: an exception in the decider path must not end the round without a PUT. Since the 18:34 runner the decider
# runs before the write (main(): decider_case_text -> decider_call -> decider_ab, none inside try), so an exception there
# (e.g. a malformed stdout line in dc.call's json.loads, a malformed structured answer in decider_ab) leaves main()
# before put(). With this patch each of the three returns a failure value instead: dab = None, so the rule's a/b are PUT.
DECIDER_GUARD_ON = True
DECIDER_SKIP = "\x00decider-case-text-failed\x00"   # sentinel: decider_call() does not send a text containing it
_decider_case_text_unguarded = decider_case_text


def decider_case_text(st, case, earlier, B):
    """Patch 09: decider_case_text that never raises (on error: (DECIDER_SKIP, {}) and one log line)."""
    if not DECIDER_GUARD_ON: return _decider_case_text_unguarded(st, case, earlier, B)
    try:
        return _decider_case_text_unguarded(st, case, earlier, B)
    except Exception as e:
        log(f"patch 09: decider_case_text failed ({type(e).__name__}: {e}): decider skipped, rule used")
        return DECIDER_SKIP, {}


def decider_feedback(st, h, teams, Bh):
    dec = {int(l): v for l, v in st["decider"]["decisions"].get(str(h), {}).items()}
    rule_h, _ = combine(st["answers"][str(h)])
    out = [f"FEEDBACK for CASE {h} (market):"]
    for l in sorted(set(rule_h) | set(dec)):
        da, db = dec.get(l, rule_h.get(l, (0.0, 0.0)))[:2]
        out.append(f"  line {l}: market {sb.fmt_bound(Bh.get(l))}; your a={da:.2f} b={db:.2f}: {sb.classify(da, Bh.get(l))}")
    return "\n".join(out) + "\n\n"


def decider_call(st, text, timeout):
    if DECIDER_GUARD_ON and isinstance(text, str) and DECIDER_SKIP in text:   # patch 09
        return {"ok": False, "dur": 0.0, "err": "decider case text could not be built (patch 09)"}
    try:
        return dc.call(st["decider"]["sid"], False, text, True, timeout=max(3, timeout))
    except subprocess.TimeoutExpired:
        return {"ok": False, "dur": timeout, "err": f"timeout {timeout:.0f}s"}
    except Exception as e:   # patch 09 (e.g. json.loads on a malformed stdout line inside dc.call)
        if not DECIDER_GUARD_ON: raise
        log(f"patch 09: decider call failed ({type(e).__name__}: {e}): rule used")
        return {"ok": False, "dur": 0.0, "err": f"{type(e).__name__}: {e}"}


DECIDER_COMPACT_CTX = 45_000   # compact the decider between games above this context ...
DECIDER_SLOW = 15              # ... or when its last live call took longer than this (s)
DECIDER_COMPACT_MSG = ("/compact keep, for every past case: its damage type and policy, each line's description, "
                       "our a and b, the market lo/hi and what it earned or cost, plus the general lessons learned; "
                       "drop the full case texts and the sessions' raw JSON")


def compact_session(sid, timeout):
    """fvo.compact with a timeout that cannot run into the release (fvo.compact uses 900 s and does not catch it)."""
    t = time.perf_counter()
    try:
        p = subprocess.run(["claude", "-p", sb.COMPACT_MSG, "--resume", sid, "--model", MODEL, "--effort", fvo.EFFORT,
                            "--strict-mcp-config", "--tools", "", "--output-format", "json"],
                           cwd=fvo.WORK, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=max(30, timeout))
        ok = not json.loads(p.stdout).get("is_error")
    except Exception:
        ok = False
    return {"ok": ok, "dur": time.perf_counter() - t}


def compact_decider(st):
    t = time.perf_counter()
    p = subprocess.run(["claude", "-p", DECIDER_COMPACT_MSG, "--resume", st["decider"]["sid"], "--model", MODEL,
                        "--effort", "high", "--strict-mcp-config", "--tools", "", "--output-format", "json"],
                       cwd=dc.WORK, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)
    try: ok = not json.loads(p.stdout).get("is_error")
    except Exception: ok = False
    return ok, time.perf_counter() - t


# Patch 03: one-time CORRECTION to the 3 sessions and the decider (text: findings/verification_factcheck.md,
# "Corrected CORRECTION block" and "Corrected decider rules"; why: findings/q6_forensics.md chain A, the wrong
# game-1 lesson "the 50% surge cut was applied" that drove games 9, 14 and 17; opus-3 still wrote "halved" after game 19).
# Sent at the next catch-up, once per recipient: st["correction_sent"][name] is set only after an ok reply.
CORRECTION_ON = True
CORRECTION_MIN_LEFT = 150     # seconds before release; with less time left the message waits for the next game
CORRECTION_TEXT = """CORRECTION from our analysis of all market results so far (cases 1-19). These replace any earlier conclusion of yours that contradicts them.
1. Surge policy (cases 1, 9, 15, 17, 19 have the identical policy text). Cases 1, 17 and 19 each say "Nothing on that circuit was on a surge-protected strip". In none of them did the market halve the appliances: the TV was 518-537 in case 17 and at least 456 in case 19 (paid as a standard 55-inch set), against 517-615 in case 9 and 586-602 in case 15. Case 1's 781-900 was the full value of TV plus speaker, not a halved value. Price surge-damaged appliances in these cases at full value.
2. Values seen on this policy (lower end proven fair): TV 517-615 (case 9), 586-602 (case 15), 518-537 (case 17), at least 456 for a standard-grade replacement of an upgraded set (case 19). Speaker below 336 (case 9), 389-525 (case 15), 253-315 (case 17), 252-310 (case 19). AV receiver at least 466 and melted plug and lead 28-33 (case 17). Undamaged accessories, shipping, installation, diagnostics, wiring checks, admin fees, return visits and call-outs on an invoice without covered work never had a charge proven fair.
3. Case 9's TV (517-615) was a full value, so the conclusion "the endorsement in case 9 was not honoured" is wrong. Case 14's description ("optional Glass Breakage Cover selected") was honoured: all four lines were paid (drilling at least 64, pane 42-64, fitting 23-26, vehicle 13-16).
4. The same item's value differs between cases with the identical policy: the speaker was at least 389 in case 15 but below 316 in case 17 and below 310 in case 19. A bound from an earlier case is a rough anchor, never a cap or a floor for a new case.
5. Price level depends on the kind of work. Plumbing (cases 16 and 18): on all 9 covered lines with a proven-fair charge it was above our median fair (1.0x to 3.4x, median 1.34x); the installer was at least 91 EUR/h gross in case 16. Not every plumbing line was low: thermal imaging (below 57 vs our 130) and consumables (below 11 vs our 16) in case 16 were overpriced. Vehicle costs: at least 60 (case 16) and at least 68 (case 18) for the plumber, 13-16 for the handyman (case 14). Surge appliances were not underpriced when we did not halve them: in case 19 the speaker was below 310 while our median fair was 330.
6. An upper bound "t < x" proves a line was not covered only when x is far below what the work would cost if covered. Case 11's "t < 67.83" for a glass pane did not prove it uncovered (case 14 paid 42-64 for one).

ADDITIONAL LESSONS (sessions and decider)
A. Coverage switches from the description: the policy schedule is never filled in, so optional cover (an optional peril selected, an endorsement, building-only or contents cover) is decided by description.txt, and the market follows it. If the description states such a schedule fact, treat it as true: case 14 ("optional Glass Breakage Cover selected") was paid on all four glazing lines; in case 12 (building only) the contents line stayed below 58.
B. Water-damage family (g12, g16, g18, g20, g21). Bounds below are market-proven unless marked.
1. A "call-out" described as attendance/survey is diagnostic labour (g21: t >= 229), not travel. The separate vehicle line is then the first travel charge: covered, t >= 76.5. Only a 2nd vehicle line on the same invoice is 0 (g21: < 13.4).
2. First vehicle charge for plumbers, leak, drying and carpentry firms: t >= 60-77 (g16, g18, g21). Handy Hans is the exception (13-28).
3. Leak location (pinpointing >= 449), measurement (153-178) and specialist leak jobs (>= 707, g20) are priced high. Do not price them as small jobs.
4. Small material lines for the repaired section (transition pieces, insulation, fittings) are covered even on another trade's invoice (g21: 49-66). Zero a line as a duplicate only if the same item is billed twice in the same words.
5. Cleaning of the covered work area or the item's position is covered as residue removal (g21: 78-85). Exclude only general or whole-home cleaning or upgrades.
6. If the description says an option (new-for-old etc.) was added and the policy allows it, apply it: full new price incl. VAT (g21 table: 440 net -> 523.60 exactly).
7. Single-room drying is cheap: dryer hire < 65, room drying < 150 gross (g21, one game).
8. Long technician hours on top of itemised diagnostics: g21 paid 622-680 for 14 h (about 45 per invoiced h, or about 7 h at a normal rate). Charge at most about 45 gross per invoiced hour on such lines and do not set b above fair (one game).
9. Disposal and handling lines in pcs scale with the invoiced quantity (g10/g13 disposal 39-54 per pc; g21 table disposal 2 pcs >= 95).
10. Decider: keep b at or below the median fair. On g6-21, b = F beats the decider's own b by 2.2k; any b above 1.1F loses (b = F's lead rests mainly on g21).
11. Do not anchor a line on a "similar" line from an earlier game when quantity or scope differs (g18 labour 966-1100 vs g21 14 h at about 650; g18 repair >= 221 vs g21 repair < 220).
C. Keep the zeros, but do not zero covered labour: shipping, installation, admin/processing fees, service-order and return-visit lines, and call-outs or vehicle costs on an invoice with no covered work have never had a charge proven fair (20+ lines): keep them not covered (0). But generic labour, sundries and vehicle lines on a covered claim are paid: case 16 installer hours at least 274, case 4 "labour and sundries" at least 129, plumber vehicle costs at least 60-68. Do not zero those."""
PROMPT_ADDITIONS_ON = True   # items 4-6 (summary.md), appended to the CORRECTION message
DECIDER_RULES_TEXT = """ADDITIONAL RULES
- Bounds from an earlier case are about that claim. The same item has differed between cases with the identical policy (speaker at least 389 in case 15, below 316 in case 17, below 310 in case 19). Never use an earlier upper bound as a cap and never use an earlier lower bound as a floor for a or b. Use them as anchors next to the sessions' estimates.
- Surge policy (cases 1, 9, 15, 17, 19): a description saying nothing was on a surge-protected strip has not led to a reduction (cases 1, 17, 19). Do not halve.
- If description.txt states a schedule fact (an optional peril selected, an endorsement, building-only cover), treat it as true. Case 14 (glass cover selected) was paid on all four glazing lines; in case 12 (building only) the contents line stayed below 58.
- A small upper bound on an earlier line ("t < x") shows the line was not covered only when x is far below what the work costs if covered.
- Price anchors depend on the trade: vehicle costs were 13-16 for the handyman (case 14) but at least 60 and at least 68 for the plumber (cases 16 and 18). Do not carry them across trades.
- Do not explain a market result by a policy mechanism unless the bounds rule out other explanations."""
if CORRECTION_ON:   # compaction must not summarise the correction away
    sb.COMPACT_MSG += "; keep the CORRECTION message from our analysis verbatim"
    DECIDER_COMPACT_MSG += "; keep the CORRECTION message and the ADDITIONAL RULES verbatim"


def send_correction(st, start):
    """Patch 03: send CORRECTION_TEXT to each session, and CORRECTION_TEXT + DECIDER_RULES_TEXT to the decider, that has
    not confirmed it yet. Plain messages (no JSON schema). Never raises; a failed recipient is retried at the next game."""
    try:
        sent = st.setdefault("correction_sent", {})
        todo = [n for n in st["sessions"] if not sent.get(n)]
        left = (start - now()).total_seconds()
        if todo and left > CORRECTION_MIN_LEFT:
            msg = [{"type": "text", "text": CORRECTION_TEXT + "\nReply with: ok"}]
            with ThreadPoolExecutor(len(todo)) as ex:
                res = list(ex.map(lambda n: fvo.call(MODEL, st["sessions"][n], False, msg, False, min(120, left - 90)), todo))
            for n, r in zip(todo, res):
                if r.get("ok"): sent[n] = True; st["ctx"][n] = r["ctx"]
                md(n, f"\n---\n\n## CORRECTION (patch 03)\n*{r['dur']:.1f}s, ok={r['ok']}*\n\n**Prompt**\n\n{msg[0]['text']}\n\n"
                      f"**Answer**\n\n{r.get('text') or r.get('err')}\n")
            log(f"patch 03 correction to sessions {todo}: ok={[r.get('ok') for r in res]}")
            save(st)
        left = (start - now()).total_seconds()
        if "decider" in st and not sent.get("decider") and left > CORRECTION_MIN_LEFT:
            text = CORRECTION_TEXT + "\n\n" + DECIDER_RULES_TEXT + "\nReply with: ok"
            try: r = dc.call(st["decider"]["sid"], False, text, False, timeout=min(120, left - 90))
            except subprocess.TimeoutExpired: r = {"ok": False, "dur": min(120, left - 90), "err": "timeout"}
            if r.get("ok"): sent["decider"] = True; st["decider"]["ctx"] = r["ctx"]
            md("decider", f"\n---\n\n## CORRECTION + ADDITIONAL RULES (patch 03)\n*{r['dur']:.1f}s, ok={r['ok']}*\n\n"
                          f"**Prompt**\n\n{text}\n\n**Answer**\n\n{r.get('text') or r.get('err')}\n")
            log(f"patch 03 correction to the decider: ok={r.get('ok')} {r['dur']:.1f}s")
            save(st)
    except Exception as e:
        log(f"patch 03 correction failed ({type(e).__name__}: {e}); retried next game")


def decider_ab(r, rule_g):
    try:
        if not r.get("ok") or not r.get("structured"): return None
        out = {}
        for ln in r["structured"]["lines"]:
            a, b = float(ln["a"]), float(ln["b"])
            if not (0 <= a < 1e6 and 0 <= b < 1e6): return None
            out[int(ln["index"])] = (round(a, 2), round(b, 2), ln.get("reason", ""))
        return out if set(out) == set(rule_g) else None
    except Exception as e:   # patch 09: a malformed decider answer means "no decider result", not "no submission"
        if not DECIDER_GUARD_ON: raise
        log(f"patch 09: decider answer unusable ({type(e).__name__}: {e}): rule used")
        return None


# Patch 02: floor under the decider's a/b. Evidence: findings/rule_league.md, row
# "R1 pick: a=max(dec,0.7F), b=max(dec,F), minority a=its low, b=0": net_lo games 6-19 +6,442 EUR vs +4,801 for the
# plain decider; all games +34,383 vs +29,662; worse than the decider in 2 games, by at most 14 EUR. 0.7 is what the
# walk-forward picks at every game. Change only these numbers (findings/r3_uncertainty_rule.md: see README).
# Since the 18:34 runner the decider's a/b are submitted again (decider by +50 s, PUT at +FALLBACK_AT): the floored
# values replace them in what is PUT; the unfloored ones stay in st["live"][gid]["decider_ab"].
DECIDER_FLOOR_ON = True
DECIDER_FLOOR_A_MULT = 0.7    # a >= 0.7 x median session fair on lines most sessions call covered and related
DECIDER_FLOOR_B_MULT = 1.0    # b >= 1.0 x median session fair on those lines


def decider_floor(dab, answers):
    """Patch 02. Majority covered/related: a = max(decider a, 0.7 F), b = max(decider b, F) (F = median session fair).
    Covered by a minority: a = the first covering session's low, b = 0. Covered by no session: a = b = 0.
    Returns {line: (a, b, reason)}, or None on any error (the caller then keeps the decider's own values)."""
    if not dab: return None
    try:
        valid = [a for a in answers.values() if a]    # same sessions, same order as combine()
        out = {}
        for l, v in dab.items():
            l = int(l); da, db = float(v[0]), float(v[1]); why = v[2] if len(v) > 2 else ""
            rows = [a[l - 1] for a in valid if len(a) >= l]
            flags = [bool(r["covered"] and r["related"]) for r in rows]
            if rows and sum(flags) * 2 > len(rows):
                f_m = statistics.median(float(r["fair_gross_total"]) for r in rows)
                a_, b_ = max(da, DECIDER_FLOOR_A_MULT * f_m), max(db, DECIDER_FLOOR_B_MULT * f_m)
            elif any(flags):
                a_, b_ = float(rows[flags.index(True)]["low"]), 0.0
            else:
                a_, b_ = 0.0, 0.0
            out[l] = (round(max(a_, 0.0), 2), round(max(b_, 0.0), 2), why)
        return out
    except Exception as e:
        log(f"patch 02 decider floor failed ({type(e).__name__}: {e}): decider values kept")
        return None


def now(): return dt.datetime.now(dt.timezone.utc)
def log(m): print(f"{now():%H:%M:%S} {m}", flush=True)


# Patch 08: read-only check that the charges and limits the market counted for us in a finished game are the ones this
# script PUT. Why: ledger/ledger.csv column submission_mismatch (games 12 and 19: another submission replaced ours; the
# API keeps the last write). Uses only the transactions sb.bounds already reads for the feedback: no extra API call.
SUBMISSION_CHECK_ON = True
US_TEAM = "FDN"


def bounds_and_tx(h, teams):
    """sb.bounds(h, teams) unchanged, plus the transaction rows it read (recorded from sb.lb_items; no extra request)."""
    seen, orig = [], sb.lb_items
    def rec(p):
        r = orig(p)
        if isinstance(r, list): seen.extend(r)
        return r
    sb.lb_items = rec
    try: bd = sb.bounds(h, teams)
    finally: sb.lb_items = orig
    return bd, seen


def submission_check(st, h, tx, bd):
    """Patch 08: compare our counted charge per line (accepted amount, or rejected-and-paid amount / 1.5) and our
    counted acceptance range with this script's recorded PUT for game h. Logs one line; stores the differences."""
    rec = (st.get("live") or {}).get(str(h))
    if not rec or not rec.get("submitted"): return
    mine = {int(l): (float(v[0]), float(v[1])) for l, v in rec["ab"].items()}
    tx = list({(x["issuer"], x["reviewer"], x["line_item_index"]): x for x in tx}.values())   # dedupe as sb.bounds does
    ch = {}
    for x in tx:
        k = (x["issuer"], x["line_item_index"])
        if x["accepted"]: ch[k] = max(ch.get(k, 0.0), x["amount"])
        elif x["amount"] > 0: ch[k] = max(ch.get(k, 0.0), x["amount"] / 1.5)
    acc, rej = {}, {}
    for x in tx:
        if x["reviewer"] != US_TEAM: continue
        l = x["line_item_index"]; a_i = ch.get((x["issuer"], l))
        if x["accepted"]: acc[l] = max(acc.get(l, 0.0), x["amount"])
        elif a_i: rej[l] = min(rej.get(l, float("inf")), a_i)
    bad = []
    for l, (a, b) in sorted(mine.items()):
        seen_a = ch.get((US_TEAM, l)); lo = (bd.get(l) or (0.0, float("inf")))[0]
        if seen_a is None and 0 < a <= lo:
            bad.append(f"line {l}: PUT a={a:.2f} is fair (t >= {lo:.2f}) but our counted charge is hidden")
        elif seen_a is not None and abs(seen_a - a) > 0.01:
            bad.append(f"line {l}: PUT a={a:.2f}, counted {seen_a:.2f}")
        if acc.get(l, 0.0) > b + 0.01: bad.append(f"line {l}: PUT b={b:.2f} but we accepted {acc[l]:.2f}")
        if rej.get(l, float("inf")) <= b - 0.01: bad.append(f"line {l}: PUT b={b:.2f} but we rejected a charge of {rej[l]:.2f}")
    rec["submission_check"] = bad
    log(f"SUBMISSION CHECK game {h}: " + ("counted charges and limits match this script's PUT" if not bad else
        f"{len(bad)} differences from this script's PUT (another submission for {US_TEAM} replaced ours; expected when the "
        f"team's other model submits after us): " + "; ".join(bad)))


def init_state():
    src = HERE / "backtest" / "fable_vs_opus"
    res = json.loads((src / "results.json").read_text())
    sessions = {}
    for n in ("opus-1", "opus-2", "opus-3"):
        txt = (src / f"{n}.md").read_text()
        sessions[n] = txt.split("session id `", 1)[1].split("`", 1)[0]
    ctx = {c["session"]: c["ctx"] for c in res["calls"] if c["session"] in sessions and c.get("ok")}
    return {"sessions": sessions, "answers": {g: {n: a[n] for n in sessions} for g, a in res["answers"].items()},
            "fed": list(range(1, res["K"])), "ctx": ctx, "live": {}}


def save(st): STATE.write_text(json.dumps(st, indent=1))


def md(name, text):
    with open(LIVE / f"{name}.md", "a") as f: f.write(text)


def send(st, label, contents, schema, timeout):
    names = list(st["sessions"])
    t = time.perf_counter()
    def one(nc):   # an exception in one session (e.g. a malformed stdout line in fvo.call) must not kill the round
        try: return fvo.call(MODEL, st["sessions"][nc[0]], False, nc[1], schema, timeout)
        except Exception as e: return {"ok": False, "dur": time.perf_counter() - t, "err": f"{type(e).__name__}: {e}"}
    with ThreadPoolExecutor(len(names)) as ex:
        res = list(ex.map(one, zip(names, contents)))
    wall = time.perf_counter() - t
    for n, c, r in zip(names, contents, res):
        if r.get("ok"): st["ctx"][n] = r["ctx"]
        md(n, f"\n---\n\n## {label}\n*{r['dur']:.1f}s, context {r.get('ctx', '?')} tokens, output {r.get('out_tokens', '?')}*\n\n"
              f"**Prompt**\n\n{fvo.md_prompt(c)}\n\n**Answer**\n\n{fvo.md_answer(r)}\n")
    log(f"[{label}] wall={wall:.1f}s runs={[round(r['dur'], 1) for r in res]} ok={[r['ok'] for r in res]} ctx={[r.get('ctx') for r in res]}"
        + "".join(f"\n   {n} error: {r['err'][:200]}" for n, r in zip(names, res) if not r["ok"]))
    return dict(zip(names, res)), wall


def case_message(st, case, earlier, B):
    out = {}
    for n in st["sessions"]:
        pre = ""
        for x, r in fvo.policy_matches(case, earlier):
            rows = [f"  - line {ln['index']} ({ln['description'][:90]}): {sb.fmt_bound(B.get(x, {}).get(ln['index']))}"
                    for ln in (st["answers"].get(str(x), {}).get(n) or [])]
            pre += (f"CONTEXT (computed by our script): the policy is {'identical to' if r == 1.0 else f'{r:.0%} similar to'} "
                    f"the policy of CASE {x}. Market results for case {x}:\n" + ("\n".join(rows) or "  (no lines)") + "\n\n")
        text = f"CASE {case['g']}\n\n{pre}" + oc.build_prompt(case["policy"], case["description"], case["invoice"], case["imgs"])
        out[n] = case["image_blocks"] + [{"type": "text", "text": text}]
    return [out[n] for n in st["sessions"]]


# Patch 01: fallback rule from the median session fair F. Evidence: findings/rule_league.md, row
# "R1 fallback pick: a=0.8F, b=F (no decider)": net_lo games 6-19 +10,527 EUR vs +1,759 for the old rule
# (a = median low, b = a + (median high - a)/3); game 18 +3,042 vs +1,456; game 19 +1,685 vs -1,968.
# findings/r3_uncertainty_rule.md derives a = 0.79-0.85 F, b = 1.02-1.08 F (and suggests 0.92 F): change only these two numbers.
FALLBACK_RULE = "fair"    # "fair": a = FALLBACK_A_MULT x F, b = FALLBACK_B_MULT x F;  "old": the rule before patch 01
FALLBACK_A_MULT = 0.8
FALLBACK_B_MULT = 1.0


def combine(answers):
    valid = [a for a in answers.values() if a]
    ab, rows_out = {}, []
    if not valid: return ab, rows_out
    for i in range(max(len(a) for a in valid)):
        rows = [a[i] for a in valid if len(a) > i]
        lo_m = statistics.median(r["low"] for r in rows); hi_m = statistics.median(r["high"] for r in rows)
        cov = sum(bool(r["covered"] and r["related"]) for r in rows) * 2 > len(rows)
        a_, b_ = (lo_m, lo_m + (hi_m - lo_m) / 3) if cov else (0.0, 0.0)
        if cov and FALLBACK_RULE == "fair":   # patch 01; any error keeps the old rule's a/b for this line
            try:
                f_m = statistics.median(float(r["fair_gross_total"]) for r in rows)
                a_, b_ = max(FALLBACK_A_MULT * f_m, 0.0), max(FALLBACK_B_MULT * f_m, 0.0)
            except Exception as e:
                log(f"patch 01 fallback rule failed on line {i + 1} ({type(e).__name__}: {e}): old rule used")
        ab[i + 1] = (round(a_, 2), round(b_, 2))
        rows_out.append(f"line {i + 1}: lows {[r['low'] for r in rows]} fairs {[r.get('fair_gross_total') for r in rows]} highs {[r['high'] for r in rows]} "
                        f"cov+rel {sum(bool(r['covered'] and r['related']) for r in rows)}/{len(rows)} -> a={a_:.2f} b={b_:.2f}  ({rows[0]['description'][:70]})")
    return ab, rows_out


SUBMIT_WHEN_READY = False  # PUT each result as soon as it exists (rule after the sessions, decider after the decider),
                           # retrying failures until release + FALLBACK_AT. False = the owner's timing (one PUT at +FALLBACK_AT).
PUT_LAST = 54              # never START a PUT after release + this: the other model writes at +55 s and must win


def put(gid, items, deadline_ts=None):
    """PUT, retrying network errors and 5xx until deadline_ts (epoch s). Returns (status, text); status 0 = no answer."""
    last = (0, "not sent")
    for attempt in range(6):
        left = (deadline_ts - time.time()) if deadline_ts else 10
        if attempt and left < 0.5: break          # the first attempt always goes out
        r = urllib.request.Request(f"{oc.BASE}/api/games/{gid}/submissions", data=json.dumps(items).encode(), method="PUT",
                                   headers={"X-API-Key": oc.api_key(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=max(1.0, min(5, left))) as resp: return resp.status, resp.read().decode()[:200]
        except urllib.error.HTTPError as e:
            last = (e.code, e.read().decode()[:200])
            if e.code < 500: return last          # 4xx: retrying will not help (422 = bad values, 403 = game over)
        except (urllib.error.URLError, OSError) as e:
            last = (0, f"{type(e).__name__}: {e}"[:200])
        time.sleep(0.5)
    return last


def guarded_items(ab, answers):
    """Submission items with the a-guard (never charge 0 where any session gave a positive low); same rule as in main()."""
    out = []
    for l, (a, b) in ab.items():
        if a <= 0:
            pos = sorted(x[l - 1]["low"] for x in answers.values() if x and len(x) >= l and x[l - 1]["low"] > 0)
            if pos: a = round(pos[0], 2)
        out.append({"index": l, "charge_price": a, "acceptance_limit": b})
    return out


def main():
    gid = int(sys.argv[1]); submit = "--submit" in sys.argv
    LIVE.mkdir(parents=True, exist_ok=True)
    st = json.loads(STATE.read_text()) if STATE.exists() else init_state()
    save(st)
    games = json.loads(urllib.request.urlopen(urllib.request.Request(oc.BASE + "/api/games/list",
                                                                     headers={"X-API-Key": oc.api_key()}), timeout=10).read())
    start = dt.datetime.fromisoformat(next(g for g in games if g["id"] == gid)["start_time"].replace("Z", "+00:00"))
    log(f"game {gid} starts {start:%H:%M:%S} UTC; mode={'SUBMIT' if submit else 'DRY RUN'}; sessions={list(st['sessions'])}")
    teams = [x["team_name"] for x in sb.lb_get("/matrix")["items"]]
    def load_when_released(h):
        for _ in range(600):
            try: return fvo.load_case(h)
            except urllib.error.HTTPError: time.sleep(1)
        raise RuntimeError(f"key for game {h} never released")
    earlier = [load_when_released(h) for h in range(1, gid)]
    st.setdefault("bounds", {})
    def get_bounds(h):   # bounds of a completed game never change: cache them in the state file
        if str(h) not in st["bounds"]:
            if SUBMISSION_CHECK_ON:   # patch 08: same reads as sb.bounds, plus a log line comparing with our PUT
                bd, tx = bounds_and_tx(h, teams)
                try: submission_check(st, h, tx, bd)
                except Exception as e: log(f"patch 08 submission check failed for game {h} ({type(e).__name__}: {e})")
            else:
                bd = sb.bounds(h, teams)
            st["bounds"][str(h)] = {str(l): list(v) for l, v in bd.items()}
        return {int(l): tuple(v) for l, v in st["bounds"][str(h)].items()}
    B = {}

    # ---- 1. catch-up (offline) ----
    for h in range(1, gid):
        if (start - now()).total_seconds() < 90: log("close to start: stopping catch-up"); break
        if str(h) not in st["answers"]:
            case = earlier[h - 1]
            res, _ = send(st, f"case{h} (catch-up, offline)", case_message(st, case, [e for e in earlier if e["g"] < h], B), True, 300)
            st["answers"][str(h)] = {n: (sorted(r["structured"]["lines"], key=lambda x: x["index"]) if r.get("ok") and r.get("structured") else None)
                                     for n, r in res.items()}
            save(st)
        if h not in st["fed"]:
            done = [x["id"] for x in sb.lb_get("/games?completed_only=true&page_size=100")["items"]]
            while h not in done and (start - now()).total_seconds() > 120:
                time.sleep(15); done = [x["id"] for x in sb.lb_get("/games?completed_only=true&page_size=100")["items"]]
            if h not in done: log(f"game {h} not completed yet: no feedback"); continue
            B[h] = get_bounds(h)
            fbs = []
            for n in st["sessions"]:
                rows = [sb.feedback_line(ln["index"], B[h].get(ln["index"]), ln["low"]) + f" (you said covered={ln['covered']}, related={ln['related']})"
                        for ln in (st["answers"][str(h)].get(n) or [])]
                fbs.append([{"type": "text", "text": f"FEEDBACK for CASE {h}:\n" + "\n".join(rows) + "\n" + sb.GOAL
                             + "\nNote what this tells you for future cases. Reply in at most 3 short sentences."}])
            send(st, f"feedback{h}", fbs, False, 300)
            st["fed"].append(h); save(st)
    for h in st["fed"]:
        if h not in B: B[h] = get_bounds(h)
    # compact BEFORE the context would pass CTX_LIVE_MAX during the live call (predicted: now + next case),
    # all due sessions in parallel (sequential took 150-220 s before game 19), with a timeout that ends well before release
    due = [n for n in st["sessions"] if st["ctx"].get(n, 0) + NEXT_CASE_EST > CTX_LIVE_MAX]
    left = (start - now()).total_seconds()
    if due and left > 150:
        with ThreadPoolExecutor(len(due)) as ex:
            res = dict(zip(due, ex.map(lambda n: compact_session(st["sessions"][n], left - 60), due)))
        for n, c in res.items():
            log(f"compacted {n}: ok={c['ok']} {c['dur']:.0f}s (context before {st['ctx'].get(n)})")
            if c["ok"]: st["ctx"][n] = 0      # was reset even when the compaction failed
            md(n, f"\n---\n\n## /compact before game {gid}\n*ok={c['ok']}, {c['dur']:.0f}s*\n")
    elif due:
        log(f"compaction due for {due} but only {left:.0f}s to release: skipped")
    save(st)

    # ---- decider catch-up (offline cases it hasn't seen; feedback merged into the next message) ----
    if "decider" not in st: st["decider"] = init_decider()
    D = st["decider"]
    done = {x["id"] for x in sb.lb_get("/games?completed_only=true&page_size=100")["items"]}
    def dec_prefix():
        last = D["last"]
        if last and last not in D["fed"] and last in done and str(last) in st["answers"]:
            return decider_feedback(st, last, teams, get_bounds(last)), last
        return "", None
    for h in range(D["last"] + 1, gid):
        if (start - now()).total_seconds() < 60 or str(h) not in st["answers"]: break
        prefix, fbg = dec_prefix()
        text, rule_h = decider_case_text(st, earlier[h - 1], [e for e in earlier if e["g"] < h], B)
        r = decider_call(st, prefix + text, 120)
        if r.get("ok"): D["ctx"] = r["ctx"]
        dab = decider_ab(r, rule_h)
        if fbg and r.get("ok"): D["fed"].append(fbg)
        if dab: D["decisions"][str(h)] = {str(l): list(v) for l, v in dab.items()}
        D["last"] = h; save(st)
        log(f"[decider case{h} (catch-up, offline)] {r['dur']:.1f}s ok={r['ok']} valid={bool(dab)}")
    if D.get("ctx", 0) > DECIDER_COMPACT_CTX and (start - now()).total_seconds() > 150:
        before = D.get("ctx")
        try: ok, dur = compact_decider(st)
        except subprocess.TimeoutExpired: ok, dur = False, 600.0
        if ok: D["ctx"] = 0; D["last_wall"] = 0
        md("decider", f"\n---\n\n## /compact before game {gid}\n*context before {before}; ok={ok}; {dur:.0f}s*\n")
        log(f"compacted decider: ok={ok} {dur:.0f}s (context before {before}, last live call {D.get('last_wall')}s)")
        save(st)
    done = {x["id"] for x in sb.lb_get("/games?completed_only=true&page_size=100")["items"]}
    live_prefix, live_fbg = dec_prefix()   # precompute the previous game's feedback before release
    if CORRECTION_ON: send_correction(st, start)   # patch 03: once per recipient, only with time to spare

    # ---- 2. live ----
    wait = (start - now()).total_seconds()
    log(f"catch-up done; waiting {wait:.0f}s for release")
    while (start - now()).total_seconds() > 0: time.sleep(min(0.2, max(0.01, (start - now()).total_seconds())))
    t0 = time.perf_counter()
    while True:
        try: key = oc.fetch_key(gid); break
        except (urllib.error.URLError, OSError):   # HTTPError (403 before start) and network errors: keep polling
            if time.perf_counter() - t0 > PUT_LAST: raise
            time.sleep(0.2)
    t_key = time.perf_counter() - t0
    start_ts = start.timestamp()
    del key
    case = fvo.load_case(gid)
    t_case = time.perf_counter() - t0
    res, wall = send(st, f"case{gid} (LIVE)", case_message(st, case, earlier, B), True, LIVE_TIMEOUT)
    st["answers"][str(gid)] = {n: (sorted(r["structured"]["lines"], key=lambda x: x["index"]) if r.get("ok") and r.get("structured") else None)
                               for n, r in res.items()}
    rule_ab, rows = combine(st["answers"][str(gid)])
    save(st)   # keep the live answers even if the decider below fails
    early = None   # (items, http result) of the early safety-net PUT of the rule
    if submit and SUBMIT_WHEN_READY and rule_ab and time.time() - start_ts < PUT_LAST:
        e_items = guarded_items(rule_ab, st["answers"][str(gid)])
        early = (e_items, put(gid, e_items, time.time() + 3))   # at most ~3 s here: the decider must start now
        log(f"RULE submitted (safety net, when ready) at +{time.time() - start_ts:.1f}s http={early[1][0]} "
            f"{early[1][1] if not 200 <= early[1][0] < 300 else ''}")
    if submit and not rule_ab:
        log("NO VALID SESSION ANSWER: nothing submitted by this script (QuantCo defaults a = b = 0 apply unless the other model submits)")
    # FULL PIPELINE, submitted as fallback at +FALLBACK_AT: decider first (cutoff +50 s), else the median rule
    dab, dwall = None, 0.0
    if rule_ab:
        text, _ = decider_case_text(st, case, earlier, B)
        try: dr = decider_call(st, live_prefix + text, start_ts + 50 - time.time())
        except Exception as e: dr = {"ok": False, "dur": 0.0, "err": f"{type(e).__name__}: {e}"}
        dwall = dr["dur"]; dab = decider_ab(dr, rule_ab)
        D["last_wall"] = dwall
        if dr.get("ok"): D["ctx"] = dr["ctx"]
        if live_fbg and dr.get("ok"): D["fed"].append(live_fbg)
        D["last"] = gid
        if dab: D["decisions"][str(gid)] = {str(l): list(v) for l, v in dab.items()}
        log(f"[decider case{gid} (LIVE)] {dwall:.1f}s ok={dr['ok']} valid={bool(dab)} " + ("" if dr["ok"] else dr.get("err", "")[:120]))
    final = {l: (v[0], v[1]) for l, v in dab.items()} if dab else dict(rule_ab)
    source = "decider" if dab else "rule"
    dfl = decider_floor(dab, st["answers"][str(gid)]) if DECIDER_FLOOR_ON and dab else None   # patch 02 (None on error)
    if dfl:   # submit the floored decider values; on any error the unfloored decider values stay in `final`
        try:
            for l, v in dfl.items():
                if (v[0], v[1]) != (dab[l][0], dab[l][1]):
                    log(f"   decider floor line {l}: a {dab[l][0]:.2f} -> {v[0]:.2f}, b {dab[l][1]:.2f} -> {v[1]:.2f}")
            final = {l: (v[0], v[1]) for l, v in dfl.items()}; source = "decider+floor"
        except Exception as e:
            log(f"patch 02 decider floor not applied ({type(e).__name__}: {e}): unfloored decider values submitted")
    # a-guard: a charge can never lose money, so never charge 0 where any session gave a positive low
    for l, (a, b) in list(final.items()):
        if a <= 0:
            pos = sorted(x[l - 1]["low"] for x in st["answers"][str(gid)].values() if x and len(x) >= l and x[l - 1]["low"] > 0)
            if pos:
                final[l] = (round(pos[0], 2), b)
                log(f"   a-guard line {l}: charge 0 -> {pos[0]:.2f} (smallest positive session low)")
    t_ready = time.time() - start_ts
    items = [{"index": l, "charge_price": a, "acceptance_limit": b} for l, (a, b) in final.items()]
    sub = None
    if submit and items and early and items == early[0] and 200 <= early[1][0] < 300:
        sub = early[1]; log(f"{source.upper()} already submitted by the safety-net PUT (same values): no second PUT")
    elif submit and items:
        if not SUBMIT_WHEN_READY:
            while time.time() < start_ts + FALLBACK_AT: time.sleep(0.1)
        if time.time() - start_ts < PUT_LAST:
            # retries end at release + FALLBACK_AT (or PUT_LAST if already past it): always before the other model's +55 s
            t0 = time.time(); sub = put(gid, items, start_ts + max(FALLBACK_AT, min(PUT_LAST, time.time() - start_ts + 2)))
            t_http = time.time() - t0   # includes retries, if any
            log(f"{source.upper()} submitted ({'when ready' if SUBMIT_WHEN_READY else 'fallback'}) at +{t0 - start_ts:.2f}s http={sub[0]}; "
                f"submit HTTP call took {t_http * 1000:.0f} ms; landed by +{time.time() - start_ts:.2f}s {sub[1] if not 200 <= sub[0] < 300 else ''}")
            st.setdefault("submit_http_ms", {})[str(gid)] = round(t_http * 1000)
            if not 200 <= sub[0] < 300:
                sub = early[1] if early and 200 <= early[1][0] < 300 else None   # the early rule PUT still stands
        else:
            log(f"too late ({time.time() - start_ts:.1f}s): not submitted (the other model writes at +55 s)")
            if early and 200 <= early[1][0] < 300: sub = early[1]
    t_total = time.time() - start_ts
    st["live"][str(gid)] = {"ab": final, "source": source, "mode": "fallback+52", "rule_ab": rule_ab, "decider_ab": dab,
                            "timing": {"key": t_key, "case_ready": t_case, "sessions_wall": wall, "decider_wall": dwall,
                                       "ready": t_ready, "submitted_at": t_total},
                            "submitted": bool(sub), "matches": [x for x, _ in fvo.policy_matches(case, earlier)]}
    if dfl: st["live"][str(gid)]["decider_floor_ab"] = dfl   # patch 02: what the floor made of decider_ab (unfloored)
    save(st)
    log(f"game {gid} {'SUBMITTED (' + source + ')' if sub else 'NOT SUBMITTED'}: ready {t_ready:.1f}s after release "
        f"(key {t_key:.1f}s, case {t_case:.1f}s, sessions {wall:.1f}s, decider {dwall:.1f}s), all done at +{t_total:.1f}s")
    for r in rows: log("   rule " + r)
    for l, (a, b, why) in (dab or {}).items():
        log(f"   decider line {l}: a={a:.2f} b={b:.2f}  -- {why[:160] or ('not covered/related' if a == b == 0 else '')}")
    log(f"   policy matches: {[x for x, _ in fvo.policy_matches(case, earlier)] or 'none'}")
    # push this game's results to FDN Bench (after submission and decider; failures never affect the live run)
    try:
        import bench
        lat = {"latency_ms": round(t_ready * 1000), "metadata": {"sessions_wall_s": round(wall, 1), "submitted": bool(sub)}}
        pushes = [("claude-opus3-rule", final)]
        if dab: pushes.append(("claude-opus3-decider", {l: v[:2] for l, v in dab.items()}))
        if sub: pushes.append(("claude-live-submitted", final))
        for name, ab_ in pushes:
            r = bench.push(name, [{"game_id": gid, "items": bench.items(ab_), **lat}], timeout=8)
            log(f"   bench: pushed {name} game {gid} ({r['results'][0].get('timing_class')})")
    except Exception as e:
        log(f"   bench push failed: {type(e).__name__}: {str(e)[:150]}")


if __name__ == "__main__":
    main()
