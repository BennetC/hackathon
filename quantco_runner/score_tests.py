"""Score blind/web/adjuster answers against market ranges [lo, hi) for t."""
import json, math, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
games = range(int(sys.argv[1]), int(sys.argv[2]) + 1)
SRC = {"blind": lambda g: HERE / "memos" / f"blind_g{g}.json",
       "web": lambda g: HERE / "persona_tests" / f"web_g{g}.json",
       "adjuster": lambda g: HERE / "persona_tests" / f"adjuster_g{g}.json"}
def verdict(f, lo, hi):
    if f >= hi: return "high"
    if f < lo: return "low"
    return "in"
def dist(f, lo, hi):  # log distance to the range (0 if inside); zero-ish handled with +10 EUR
    if lo <= f < hi: return 0.0
    edge = hi if f >= hi else lo
    return abs(math.log((f + 10) / (edge + 10)))
tot = {m: {"in": 0, "high": 0, "low": 0, "d": [], "miss": 0} for m in SRC}
rows = []
for g in games:
    for m, path in SRC.items():
        p = path(g)
        if not p.exists():
            tot[m]["miss"] += 1; continue
        d = json.loads(p.read_text())
        R = {int(k): v for k, v in d["ranges"].items()}
        for L in d["answer"]["lines"]:
            if L["index"] not in R: continue
            lo, hi = R[L["index"]]; f = L["fair_gross_total"]
            v = verdict(f, lo, hi); tot[m][v] += 1; tot[m]["d"].append(dist(f, lo, hi))
            rows.append((g, L["index"], m, f, lo, hi, v))
print(f"{'test':9} {'lines':>5} {'in':>4} {'high':>5} {'low':>4} {'in%':>5} {'mean|log err|':>14} missing_runs")
for m, t in tot.items():
    n = t["in"] + t["high"] + t["low"]
    print(f"{m:9} {n:5} {t['in']:4} {t['high']:5} {t['low']:4} {100*t['in']/max(n,1):5.0f} "
          f"{sum(t['d'])/max(n,1):14.3f} {t['miss']}")
print()
from itertools import groupby
for (g, i), grp in groupby(sorted(rows), key=lambda r: (r[0], r[1])):
    grp = {r[2]: r for r in grp}; any_ = next(iter(grp.values()))
    cells = "  ".join(f"{m}={grp[m][3]:>8.0f} {grp[m][6]:4}" if m in grp else f"{m}=      -     " for m in SRC)
    print(f"g{g:<2} L{i:<2} range=[{any_[4]:>8.2f}, {any_[5]:>8.2f})  {cells}")
