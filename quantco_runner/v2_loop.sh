#!/usr/bin/env bash
# Pipeline v2, RECORD ONLY (never submits). Stop with: pkill -f '^bash ./v2_loop.sh'
cd "$(dirname "$0")"
for g in $(seq "${1:-23}" 100); do
  echo "===== v2 game $g =====" >> backtest/v2/v2.log
  uv run --script v2_record.py "$g" >> backtest/v2/v2.log 2>&1
  echo "===== v2 game $g exit $? =====" >> backtest/v2/v2.log
done
