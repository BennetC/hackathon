#!/usr/bin/env bash
# Submit every game live with the Opus session pipeline, one after another. Stop with: pkill -f live_loop.sh
cd "$(dirname "$0")"
start=${1:-12}
for g in $(seq "$start" 100); do
  echo "===== game $g =====" >> backtest/live/live.log
  uv run --script live_opus.py "$g" --submit >> backtest/live/live.log 2>&1
  echo "===== game $g exit $? =====" >> backtest/live/live.log
done
