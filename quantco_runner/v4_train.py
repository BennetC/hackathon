#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyzipper", "pillow"]
# ///
"""Train ONE fresh Fable 5.2 session with v4_system_prompt.txt passed as a real system prompt (--system-prompt on
every call). Same case loop, price book, policy note, market feedback and 30 s cutoff as v3_train.py, so the result
is directly comparable with v3-fable-b. Own state/work dir (backtest/v4_train); never submits, never pushes to Bench,
never touches the live v3 sessions.
usage: uv run --script v4_train.py [first_case] [last_case]
"""
import json, pathlib, subprocess, sys, time, types

HERE = pathlib.Path(__file__).resolve().parent
SYSTEM = (HERE / "v4_system_prompt.txt").read_text()

sys.modules["bench"] = types.SimpleNamespace(push=lambda *a, **k: None, items=lambda ab: [])  # no Bench pushes
import v3_train as v3  # noqa: E402
import v2_record as v2  # noqa: E402

v3.OUT = HERE / "backtest" / "v4_train"
v3.STATE = v3.OUT / "state.json"
v2.WORK = v3.OUT / "work"
v3.RESEARCHERS = [{"slot": "fable-v4", "model": "claude-fable-5-2", "effort": "medium"}]
v3.CORE, v3.VARIANT, v2.RULE30 = "", {"fable-v4": ""}, ""   # rules live in the system prompt; first message is just "ok"
# price-book header: same corrected recency wording as the system prompt (v3's says "price level drifts", which the data does not show)
v3.RECENCY = ("NEWEST COMPARABLE ROW WINS: there is no overall price trend across cases, but the same item, role or fee is priced "
              "differently from case to case. When rows conflict, use the most recent comparable row rather than an average.")
# per-case feedback: drop "This newest result counts much more than older ones" (invites over-reacting to one case)
_v3_feedback = v3.feedback
def _feedback(*a, **k):
    return _v3_feedback(*a, **k).replace(
        "This newest result counts much more than older ones.",
        "Use it for the same items, roles and fees in later cases; do not shift unrelated prices because of one case.")
v3.feedback = _feedback
# same compaction rule as v3 (compact past 120k tokens), but the /compact call also gets the system prompt
_real_run = subprocess.run
def _run(cmd, *a, **k):
    if isinstance(cmd, list) and cmd[:3] == ["claude", "-p", cmd[2]] and str(cmd[2]).startswith("/compact"):
        cmd = cmd + ["--system-prompt", SYSTEM]
    return _real_run(cmd, *a, **k)
v2.subprocess = types.SimpleNamespace(run=_run, DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired)


def cli_call(model, effort, sid, first, content, schema, timeout, cwd=None):
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", model, "--effort", effort, "--strict-mcp-config", "--tools", "", "--autocompact", "1000000",
           "--system-prompt", SYSTEM, *(["--session-id", sid] if first else ["--resume", sid])]
    if schema: cmd += ["--json-schema", json.dumps(schema)]
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
    t = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=cwd or v2.WORK, input=msg, capture_output=True, text=True, timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        return {"ok": False, "cutoff": True, "dur": time.perf_counter() - t, "err": f"cut off after {timeout:.0f}s"}
    dur = time.perf_counter() - t
    ev = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
    res = [e for e in ev if e.get("type") == "result"]
    if not res or res[-1].get("is_error"):
        return {"ok": False, "cutoff": False, "dur": dur, "err": str(res[-1].get("result") if res else p.stderr[-300:])[:300]}
    r = res[-1]; u = r.get("usage") or {}; last = (u.get("iterations") or [u])[-1]
    return {"ok": True, "cutoff": False, "dur": dur, "structured": r.get("structured_output"), "cum_cost": r.get("total_cost_usd"),
            "ctx": last.get("input_tokens", 0) + last.get("cache_creation_input_tokens", 0) + last.get("cache_read_input_tokens", 0)}


v2.cli_call = cli_call

if __name__ == "__main__":
    v3.main()
