"""Run blind/memo, web and adjuster tests on a range of games, then score against market ranges."""
import json, math, pathlib, pickle, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
HERE = pathlib.Path(__file__).resolve().parent
games = range(int(sys.argv[1]), int(sys.argv[2]) + 1)
jobs = [(g, m) for g in games for m in ("memo", "web", "adjuster")]
def run(job):
    g, m = job
    cmd = ["uv", "run", "--script", "memo_writer.py", str(g)] if m == "memo" else \
          ["uv", "run", "--script", "persona_tests.py", str(g), "--mode", m]
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    (HERE / "batch_logs").mkdir(exist_ok=True)
    (HERE / "batch_logs" / f"{m}_g{g}.log").write_text(p.stdout + p.stderr)
    print(f"done {m} g{g} rc={p.returncode}", flush=True)
with ThreadPoolExecutor(4) as ex:
    list(ex.map(run, jobs))
