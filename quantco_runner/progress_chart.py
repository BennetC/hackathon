"""Rolling accuracy over training cases for v4 fable vs v3 sessions -> HTML small multiples (inline SVG)."""
import json, math, sys, pathlib
Q = pathlib.Path(__file__).resolve().parent
R = json.load(open(Q / "all_ranges.json"))
V4 = json.load(open(Q / "backtest/v4_train/state.json"))["games"]
T = json.load(open(Q / "backtest/v3_train/state.json"))["games"]
L = json.load(open(Q / "backtest/v2/state.json"))["games"]
def v3(slot, live):
    return lambda g: (T.get(str(g), {}).get("answers") or {}).get(slot) or ((L.get(str(g), {}).get("v3_answers") or {}).get(live))
S = [("v4 Fable (new prompt)", lambda g: (V4.get(str(g), {}).get("answers") or {}).get("fable-v4"), "--s1"),
     ("v3 fable-b", v3("fable-b", "v3-fable-b"), "--s2"),
     ("v3 fable-a", v3("fable-a", "v3-fable-a"), "--s3"),
     ("v3 opus-c", v3("opus-c", "v3-opus-c"), "--s4")]
LAST = max(int(g) for g in V4)
W = 8
data = {}
for name, f, _ in S:
    per = {}
    for g in range(1, LAST + 1):
        a = f(g); n = k = 0
        for x in a or []:
            r = R.get(str(g), {}).get(str(x["index"]))
            if not r or (r[0] == 0 and math.isinf(r[1])): continue
            v = x["fair_gross_total"] if (x["covered"] and x["related"]) else 0.0
            n += 1; k += r[0] <= v < r[1]
        if a is None:
            n = sum(1 for l, r in R.get(str(g), {}).items() if not (r[0] == 0 and math.isinf(r[1])))  # missed case counts as 0 in range
        per[g] = (k, n)
    pts = []
    for g in range(W, LAST + 1):
        kk = sum(per[h][0] for h in range(g - W + 1, g + 1)); nn = sum(per[h][1] for h in range(g - W + 1, g + 1))
        if nn: pts.append((g, 100 * kk / nn, kk, nn))
    data[name] = pts
json.dump({"last": LAST, "window": W, "series": [[n, c, data[n]] for n, _, c in S]}, open(sys.argv[1], "w"))
print(LAST, {n: (p[-1][1] if p else None) for n, p in data.items()})
