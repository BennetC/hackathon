"""After each newly completed game (never within 60 s of a release): refresh the research CSV ledger (read-only) and
write the per-source track record tables for v1 and v2. Log: backtest/ledger_loop.log"""
import json, pathlib, subprocess, sys, time, urllib.request, datetime as dt
R = pathlib.Path.home() / "dev/quantco-runner"; RES = pathlib.Path.home() / ".t3-nightly/projects/quantco-c2f-pricing-research-2"
sys.path.insert(0, str(R))
LB = "https://c2f.public.quantco.cloud/leaderboard/api"
def log(m): print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {m}", flush=True)
def get(p): return json.load(urllib.request.urlopen(LB + p, timeout=15))
seen = set()
while True:
    try:
        now = time.time()
        starts = [dt.datetime.fromisoformat(g["start_time"].replace("Z", "+00:00")).timestamp() for g in get("/games?page_size=100")["items"]]
        if any(abs(now - s) < 60 or 0 <= s - now < 60 for s in starts):
            time.sleep(15); continue
        done = {x["id"] for x in get("/games?completed_only=true&page_size=100")["items"]}
        new = sorted(done - seen)
        if new and seen:
            log(f"new completed game(s) {new}: refreshing ledger")
            p = subprocess.run(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=2G", "-p", "MemorySwapMax=0", "timeout", "180",
                                "python3", "-I", "tools/update_ledger.py", "--refresh"], cwd=RES, capture_output=True, text=True)
            log("ledger: " + (p.stdout.strip().splitlines() or ["(no output)"])[-1][:200] + (f" rc={p.returncode}" if p.returncode else ""))
            try:
                import live_opus as v1
                st = json.loads((R / "backtest/live/state.json").read_text())
                B = {int(g): {int(l): tuple(v) for l, v in b.items()} for g, b in st.get("bounds", {}).items()}
                (R / "backtest/live/track_record.txt").write_text(v1.track_record(st, B))
                v2p = R / "backtest/v2/state.json"
                if v2p.exists():
                    s2 = json.loads(v2p.read_text()); lab = json.loads((R / "backtest/v2/labels.json").read_text())
                    lab_st = {"answers": {g: {lab[s]: a for s, a in v["answers"].items() if a} for g, v in s2["games"].items()}}
                    import session_backtest as sb
                    B2 = {}
                    for g in s2["games"]:
                        if int(g) in done: B2[int(g)] = B.get(int(g)) or sb.bounds(int(g), [x["team_name"] for x in sb.lb_get("/matrix")["items"]])
                    (R / "backtest/v2/track_record.txt").write_text(v1.track_record(lab_st, B2))
                log("track records written (backtest/live/track_record.txt, backtest/v2/track_record.txt)")
            except Exception as e:
                log(f"track record failed: {type(e).__name__}: {e}")
        seen |= done
    except Exception as e:
        log(f"error: {type(e).__name__}: {e}")
    time.sleep(30)
