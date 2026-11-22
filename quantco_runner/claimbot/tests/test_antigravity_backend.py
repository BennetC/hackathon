"""Tests for AntigravityBackend (ACP) and Daniil image preparation."""

from __future__ import annotations

import io
import json
import stat
from pathlib import Path

import pytest
from PIL import Image

from claimbot.llm import AntigravityBackend, LLMError
from claimbot.llm.antigravity_backend import (
    LOCKED_AGENT_NAME,
    LOCKED_APP_DATA_DIR,
    extract_json_object,
    normalize_model_slug,
)
from claimbot.preprocessing.images import (
    DANIIL_MAX_SIDE,
    prepare_daniil_image,
    stage_daniil_images,
)


def _exe(dirpath: Path, name: str, body: str) -> Path:
    p = dirpath / name
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def _make_acp_stub(dirpath: Path, log_path: Path, *, send_perm_request: bool = False) -> Path:
    return _exe(
        dirpath,
        "agy-acp",
        f"""
import json, sys, uuid

args = sys.argv[1:]
log_file = {str(log_path)!r}
send_perm = {send_perm_request!r}

def log(entry):
    with open(log_file, "a") as fh:
        fh.write(json.dumps(entry) + "\\n")

log({{"event": "spawn", "args": args}})

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()

while True:
    raw = sys.stdin.readline()
    if not raw:
        break
    raw = raw.strip()
    if not raw:
        continue
    msg = json.loads(raw)
    if "method" not in msg:
        continue
    rid, m, p = msg["id"], msg["method"], msg.get("params") or {{}}
    log({{"event": "rpc", "method": m, "params": p}})
    if m == "initialize":
        emit({{"jsonrpc": "2.0", "id": rid, "result": {{"protocolVersion": 1}}}})
    elif m == "session/new":
        emit({{"jsonrpc": "2.0", "id": rid, "result": {{"sessionId": str(uuid.uuid4())}}}})
    elif m == "session/load":
        emit({{"jsonrpc": "2.0", "id": rid, "result": {{"sessionId": p["sessionId"]}}}})
    elif m == "session/set_model":
        emit({{"jsonrpc": "2.0", "id": rid, "result": {{}}}})
    elif m == "session/prompt":
        sid = p["sessionId"]
        blocks = p.get("prompt") or []
        text = "\\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if send_perm:
            emit({{"jsonrpc": "2.0", "id": 9999, "method": "session/request_permission",
                  "params": {{"sessionId": sid, "options": [{{"optionId": "reject_once", "kind": "reject_once"}}]}}}})
            log({{"event": "perm_reply", "reply": json.loads(sys.stdin.readline())}})
        reply = "compacted" if text.startswith("/compact") else '{{"ok": true}}'
        usage = {{"inputTokens": 2000, "cachedReadTokens": 500, "cachedWriteTokens": 0, "outputTokens": 20, "thoughtTokens": 5}}
        emit({{"jsonrpc": "2.0", "method": "session/update", "params": {{"sessionId": sid, "update": {{"sessionUpdate": "agent_message_chunk", "content": {{"type": "text", "text": reply}}}}}}}})
        emit({{"jsonrpc": "2.0", "id": rid, "result": {{"stopReason": "end_turn", "usage": usage}}}})
""",
    )


def test_daniil_image_preserves_raw_under_5mb_and_downscales_over_threshold(tmp_path):
    small = tmp_path / "photo_small.png"
    Image.new("RGB", (600, 400), (10, 20, 30)).save(small, format="PNG")
    mt, data, ext = prepare_daniil_image(small)
    assert mt == "image/png" and ext == ".png" and data == small.read_bytes()

    big = tmp_path / "photo_big.png"
    Image.new("RGB", (2400, 1800), (120, 80, 40)).save(big, format="PNG")
    mt2, data2, ext2 = prepare_daniil_image(big, max_b64_bytes=100)
    assert mt2 == "image/jpeg" and ext2 == ".jpg"
    with Image.open(io.BytesIO(data2)) as im:
        assert max(im.size) == DANIIL_MAX_SIDE


def test_stage_daniil_images_keeps_all_photos_sorted(tmp_path):
    src = tmp_path / "case"
    src.mkdir()
    photos = []
    for i in range(6):
        p = src / f"photo_{i}.jpg"
        Image.new("RGB", (80, 60), (i * 30, 10, 20)).save(p, format="JPEG")
        photos.append(p)
    staged = stage_daniil_images(list(reversed(photos)), tmp_path / "staged", base_dir=src)
    assert [rel for rel, _ in staged] == [f"photo_{i}.jpg" for i in range(6)]


def test_normalize_model_slug_and_json_extract():
    assert normalize_model_slug("gemini-4-neon", "high") == ("gemini-4-neon-high", None)
    assert normalize_model_slug(None, "low") == ("gemini-4-neon-low", None)
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_antigravity_acp_inline_images_zero_tools_and_warm_reuse(tmp_path):
    log_path = tmp_path / "acp_log.jsonl"
    bin_file = _make_acp_stub(tmp_path, log_path, send_perm_request=True)
    llm = AntigravityBackend(model="gemini-4-neon-low", bin_path=str(bin_file))
    try:
        photo = tmp_path / "p.png"
        Image.new("RGB", (64, 64), "red").save(photo, format="PNG")
        gdir = tmp_path / "acp_gemini"
        wd = tmp_path / "wd"

        out = llm.ask("TASK", shared_context="CTX", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}}, images=[photo])
        assert out == {"ok": True}

        t1 = llm.run_session_turn("RULES", cwd=wd, session_key="w1", gemini_dir=gdir, timeout_s=10)
        t2 = llm.run_session_turn(
            "CASE", cwd=wd, conversation_id=t1.conversation_id,
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            images=[photo], session_key="w1", gemini_dir=gdir, timeout_s=10,
        )
        tc = llm.compact_session(t1.conversation_id, "/compact keep", cwd=wd, session_key="w1", gemini_dir=gdir)
        assert t2.conversation_id == t1.conversation_id and t2.structured_output == {"ok": True}
        assert tc.text == "compacted" and tc.context_tokens == 2500

        assert json.loads((gdir / "config" / "mcp_config.json").read_text()) == {"mcpServers": {}}
        agent_md = (gdir / "config" / "agents" / LOCKED_AGENT_NAME / "agent.md").read_text()
        assert "tools: []" in agent_md and "commandExecutionPolicy: off" in agent_md
        settings = json.loads((gdir / LOCKED_APP_DATA_DIR / "settings.json").read_text())
        assert "command(*)" in settings["permissions"]["deny"] and "mcp(*)" in settings["permissions"]["deny"]

        events = [json.loads(line) for line in log_path.read_text().splitlines()]
        spawns = [e for e in events if e["event"] == "spawn"]
        assert len(spawns) == 2
        prompts = [e["params"]["prompt"] for e in events if e["event"] == "rpc" and e["method"] == "session/prompt"]
        assert prompts[0][0]["type"] == "image" and prompts[0][1]["type"] == "text"
        perm_replies = [e["reply"] for e in events if e["event"] == "perm_reply"]
        assert perm_replies[0]["result"]["outcome"]["optionId"] == "reject_once"
    finally:
        llm.close()

    slow = _exe(
        tmp_path,
        "agy-slow",
        """
import json, sys, time
while True:
    raw = sys.stdin.readline()
    if not raw:
        break
    m = json.loads(raw)
    if m.get("method") == "initialize":
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": 1}}), flush=True)
    else:
        time.sleep(30)
""",
    )
    slow_llm = AntigravityBackend(bin_path=str(slow))
    try:
        with pytest.raises(LLMError, match="timed out"):
            slow_llm.run_session_turn("hi", cwd=tmp_path, timeout_s=1.0)
    finally:
        slow_llm.close()
