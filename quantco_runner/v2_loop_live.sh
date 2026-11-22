#!/usr/bin/env bash
# Pipeline v2 LIVE: Fable judge submits LAST at release + 57 s. Stop with: pkill -f '^bash ./v2_loop_live.sh'
cd "$(dirname "$0")"
for g in $(seq "${1:-30}" 100); do
  echo "===== v2 LIVE game $g =====" >> backtest/v2/v2.log
  uv run --script v2_record.py "$g" --submit >> backtest/v2/v2.log 2>&1
  echo "===== v2 game $g exit $? =====" >> backtest/v2/v2.log
done
