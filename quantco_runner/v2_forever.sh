#!/usr/bin/env bash
# Always-on v2 LIVE runner (Fable + 2 Opus researchers, Fable judge, submits at release + 57 s).
# Picks the next game itself (first game whose release is less than 45 s ago or in the future) and runs it.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
while true; do
  g=$(python3 -I -c '
import json, urllib.request, datetime as dt, pathlib
k = [l.split("=", 1)[1].strip() for l in pathlib.Path(".env").read_text().splitlines() if l.startswith("TEAM_API_KEY=")][0]
r = urllib.request.Request("https://c2f.public.quantco.cloud/api/games/list", headers={"X-API-Key": k})
now = dt.datetime.now(dt.timezone.utc).timestamp()
gs = sorted((dt.datetime.fromisoformat(g["start_time"].replace("Z", "+00:00")).timestamp(), g["id"]) for g in json.loads(urllib.request.urlopen(r, timeout=15).read()))
nxt = [gid for t, gid in gs if t > now - 45]
print(nxt[0] if nxt else "")' 2>/dev/null)
  if [ -z "$g" ]; then sleep 60; continue; fi
  echo "===== v2 LIVE game $g ($(date -u +%T)) =====" >> backtest/v2/v2.log
  uv run --script v2_record.py "$g" --submit >> backtest/v2/v2.log 2>&1
  rc=$?
  echo "===== v2 game $g exit $rc =====" >> backtest/v2/v2.log
  # never start the same game twice in a row: wait until its window has passed
  sleep 20
done
