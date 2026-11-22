"""Games 53-57: each of our 9 trained live sessions vs the 1x Opus pricing-book model (and plain), same a/b rule.
Line accuracy against market ranges + counterfactual FDN net (fable_vs_opus.replay, other teams unchanged)."""
import json, math, pickle, statistics as st, sys
sys.path.insert(0, ".")
import formula as fx
from fable_vs_opus import replay
G = range(53, 58)
TX = pickle.load(open("live_eval/tx_47plus.pkl", "rb"))
S = json.load(open("backtest/v2/state.json"))["games"]
SESS = ["v1-opus-1", "v1-opus-2", "v1-opus-3", "opus-1", "opus-2", "fable-1", "v3-fable-a", "v3-fable-b", "v3-opus-c"]

def fairs(lines):
    return {L["index"]: (float(L["fair_gross_total"]) if L.get("covered", True) and L.get("related", True) else 0.0) for L in lines}

src = {}  # name -> g -> {line: fair}
for g in G:
    v = S[str(g)]; ans = {**(v.get("answers") or {}), **(v.get("v3_answers") or {})}
    for s in SESS:
        if ans.get(s): src.setdefault(s, {})[g] = fairs(ans[s])
    allf = [src[s][g] for s in SESS if g in src.get(s, {})]
    src.setdefault("median of 9", {})[g] = {l: st.median(f[l] for f in allf if l in f) for l in allf[0]}
    for m in ("book", "plain"):
        src.setdefault(f"{m} (1x Opus xhigh)", {})[g] = fairs(json.load(open(f"book_test/{m}_g{g}.json"))["answer"]["lines"])

teams = sorted({x["issuer"] for g in G for x in TX[g][1]} | {x["reviewer"] for g in G for x in TX[g][1]})
rows = []
for name, per in src.items():
    n = inn = hi_ = lo_ = 0; err = 0.0; net_lo = net_hi = 0.0; pg = {}
    for g in G:
        bd, tx = TX[g]
        f = per.get(g)
        if not f: continue
        for l, x in f.items():
            r = bd.get(l)
            if not r or (r[0] == 0 and math.isinf(r[1])): continue
            n += 1
            if x >= r[1]: hi_ += 1; err += abs(math.log((x + 10) / (r[1] + 10)))
            elif x < r[0]: lo_ += 1; err += abs(math.log((x + 10) / (r[0] + 10)))
            else: inn += 1
        ab = {l: fx.line_ab([x]) for l, x in f.items()}
        rp = replay(g, ab, tx, teams, bd)
        net_lo += rp["net_lo"]; net_hi += rp["net_hi"]; pg[g] = (rp["net_lo"] + rp["net_hi"]) / 2
    rows.append((name, n, inn, hi_, lo_, err / max(n, 1), net_lo, net_hi, pg))
rows.sort(key=lambda r: -(r[6] + r[7]))
print(f"{'source':22} {'lines':>5} {'in':>3} {'hi':>3} {'lo':>3} {'in%':>4} {'log err':>7} {'net (worst..best)':>22} {'mid':>8} | " + " ".join(f"{'g'+str(g):>7}" for g in G))
for name, n, inn, h, l, e, a, b, pg in rows:
    print(f"{name:22} {n:5} {inn:3} {h:3} {l:3} {100*inn/max(n,1):4.0f} {e:7.3f} {a:>10.0f}..{b:<10.0f} {(a+b)/2:8.0f} | " + " ".join(f"{pg.get(g,0):7.0f}" for g in G))
