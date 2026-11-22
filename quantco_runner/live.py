"""LIVE: for game N, submit a safe fallback at release, then overwrite with Opus a/b. SUBMITS to QuantCo.
usage: uv run --with pyzipper --with pillow python live.py <game_id>
Fallback (instant): a=0, b=1e6 for lines 1..20 (never pays the 1.5x penalty).
Then: opus_case.py --runs 3 --effort high --timeout 40 -> a=low, b=low+(high-low)/3 (0/0 if not covered/related)."""
import json, re, subprocess, sys, time, urllib.request, urllib.error, datetime as dt, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import opus_case as o
gid = int(sys.argv[1]); HERE = pathlib.Path(__file__).resolve().parent
log = lambda m: print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S.%f}"[:-3] + f" game={gid} {m}", flush=True)
def put(items):
    r = urllib.request.Request(f"{o.BASE}/api/games/{gid}/submissions", data=json.dumps(items).encode(), method="PUT",
                               headers={"X-API-Key": o.api_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp: return resp.status, resp.read().decode()[:200]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:200]
games = json.loads(urllib.request.urlopen(urllib.request.Request(o.BASE + "/api/games/list", headers={"X-API-Key": o.api_key()}), timeout=10).read())
start = dt.datetime.fromisoformat(next(g for g in games if g["id"] == gid)["start_time"].replace("Z", "+00:00")).timestamp()
while time.time() < start: time.sleep(min(0.2, max(0.01, start - time.time())))
while True:
    try: o.fetch_key(gid); break
    except urllib.error.HTTPError: time.sleep(0.2)
st, body = put([{"index": i, "charge_price": 0.0, "acceptance_limit": 1e6} for i in range(1, 21)])
log(f"fallback http={st} t={time.time() - start:.1f}s {'' if st < 300 else body}")
p = subprocess.run(["uv", "run", "--script", str(HERE / "opus_case.py"), str(gid), "--runs", "3", "--effort", "high", "--timeout", "40"],
                   capture_output=True, text=True, timeout=55)
(HERE / "live_eval" / f"live_game{gid}.txt").write_text(p.stdout + p.stderr)
items = []
for line in p.stdout.splitlines():
    m = re.match(r"\s+(\d+)\s+\d+/\d+\s+\d+/\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", line)
    if m: items.append({"index": int(m.group(1)), "charge_price": round(float(m.group(5)), 2), "acceptance_limit": round(float(m.group(6)), 2)})
if not items:
    log(f"opus produced nothing, fallback stays. t={time.time() - start:.1f}s"); sys.exit(1)
if time.time() - start > 58:
    log("too late, fallback stays"); sys.exit(1)
st, body = put(items)
log(f"opus http={st} t={time.time() - start:.1f}s items={items} {'' if st < 300 else body}")
