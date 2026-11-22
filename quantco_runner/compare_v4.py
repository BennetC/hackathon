"""v4 fable (new system prompt) vs the v3 sessions and other trained sessions: line accuracy (cases 1-57) and money (36-57)."""
import json, math, pickle, sys
sys.path.insert(0, ".")
import formula as fx
from fable_vs_opus import replay
R = json.load(open("all_ranges.json"))
V4 = json.load(open("backtest/v4_train/state.json"))["games"]
T = json.load(open("backtest/v3_train/state.json"))["games"]
L = json.load(open("backtest/v2/state.json"))["games"]
TX = {**pickle.load(open("live_eval/tx_36plus.pkl", "rb")), **pickle.load(open("live_eval/tx_47plus.pkl", "rb"))}
def v3(slot, live): return lambda g: (T.get(str(g), {}).get("answers") or {}).get(slot) or (L.get(str(g), {}).get("v3_answers") or {}).get(live)
S = {"v4 fable (new prompt)": lambda g: (V4.get(str(g), {}).get("answers") or {}).get("fable-v4"),
     "v3 fable-b": v3("fable-b", "v3-fable-b"), "v3 fable-a": v3("fable-a", "v3-fable-a"), "v3 opus-c": v3("opus-c", "v3-opus-c")}
def fair(x): return float(x["fair_gross_total"]) if (x["covered"] and x["related"]) else 0.0
teams = sorted({x[k] for g in TX for x in TX[g][1] for k in ("issuer", "reviewer")})
def acc(name, f, gs):
    n = k = hi = lo = 0; e = 0.0; miss = 0
    for g in gs:
        a = f(g)
        if not a: miss += 1; continue
        for x in a:
            r = R.get(str(g), {}).get(str(x["index"]))
            if not r or (r[0] == 0 and math.isinf(r[1])): continue
            v = fair(x); n += 1
            if v >= r[1]: hi += 1; e += math.log((v + 10) / (r[1] + 10))
            elif v < r[0]: lo += 1; e += math.log((r[0] + 10) / (v + 10))
            else: k += 1
    return n, k, hi, lo, e / max(n, 1), miss
def money(f, gs):
    lo_ = hi_ = 0.0
    for g in gs:
        a = f(g)
        if not a or g not in TX: continue
        bd, tx = TX[g]
        rp = replay(g, {x["index"]: fx.line_ab([fair(x)]) for x in a}, tx, teams, bd)
        lo_ += rp["net_lo"]; hi_ += rp["net_hi"]
    return lo_, hi_
for lab, gs in [("cases 1-57", range(1, 58)), ("cases 1-39 (old run, before compaction)", range(1, 40)), ("cases 40-57 (after compaction)", range(40, 58))]:
    print(f"\n{lab}\n{'session':24} {'lines':>5} {'in':>4} {'in%':>4} {'high':>4} {'low':>4} {'logerr':>6} {'missing':>7}")
    for name, f in S.items():
        n, k, h, l, e, m = acc(name, f, gs)
        print(f"{name:24} {n:5} {k:4} {100*k/max(n,1):4.0f} {h:4} {l:4} {e:6.3f} {m:7}")
print("\nmoney: FDN net if this session's prices alone were submitted (a=0.92x, b=1.04x), other teams unchanged")
for lab, gs in [("games 36-57", range(36, 58)), ("games 48-57", range(48, 58))]:
    print(lab)
    for name, f in S.items():
        a, b = money(f, gs); print(f"  {name:24} {a:>9.0f} .. {b:<9.0f} mid {(a+b)/2:9.0f}")
