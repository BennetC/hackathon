"""CLI agent providers, tested against stand-in `claude` / `codex` executables."""

import json
import os
import stat
from pathlib import Path

import pytest

from claimbot.llm import LLMError, LLMRequest
from claimbot.llm.cli_backends import ClaudeCodeLLM, CodexLLM

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"],
          "additionalProperties": False}


def _exe(dirpath: Path, name: str, body: str) -> None:
    p = dirpath / name
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def bin_dir(tmp_path, monkeypatch):
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", f"{d}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    return d


def test_claude_code_isolated_call(bin_dir, tmp_path):
    log = tmp_path / "claude_args.json"
    _exe(bin_dir, "claude", f'''
import json, os, sys
args = sys.argv[1:]
sysprompt = open(args[args.index("--system-prompt-file") + 1]).read()
msg = json.loads(sys.stdin.readline())
json.dump({{"args": args, "content": msg["message"]["content"], "system": sysprompt,
           "api_key_seen": "ANTHROPIC_API_KEY" in os.environ, "cwd_files": os.listdir(".")}},
          open({str(log)!r}, "w"))
print(json.dumps({{"type": "system", "subtype": "init"}}))
print(json.dumps({{"type": "result", "is_error": False, "subtype": "success",
                  "structured_output": {{"x": 7}},
                  "usage": {{"input_tokens": 5, "cache_read_input_tokens": 100, "output_tokens": 9}}}}))
''')
    llm = ClaudeCodeLLM()
    from PIL import Image
    img = tmp_path / "photo.png"
    Image.new("RGB", (2000, 1500), "blue").save(img)
    out = llm.complete_json(LLMRequest(shared_context="CASE", task="TASK", schema=SCHEMA,
                                       model="sonnet", effort="low", timeout_s=10, images=[img]))
    assert out == {"x": 7}
    seen = json.loads(log.read_text())
    a = seen["args"]
    assert a[a.index("--tools") + 1] == "" and "--no-session-persistence" in a
    assert a[a.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in a
    assert "--disable-slash-commands" in a
    assert a[a.index("--model") + 1] == "sonnet" and a[a.index("--effort") + 1] == "low"
    assert json.loads(a[a.index("--json-schema") + 1]) == SCHEMA
    assert a[a.index("--input-format") + 1] == "stream-json"
    assert seen["content"][0]["type"] == "image" and seen["content"][-1] == {"type": "text", "text": "TASK"}
    assert seen["system"] == "CASE"
    assert seen["api_key_seen"] is False                 # runs on the subscription
    assert seen["cwd_files"] == ["system.txt"]           # empty, private working dir
    assert llm.take_usage() == {"calls": 1, "input": 105, "cached_input": 100, "output": 9}


def test_claude_code_error_and_timeout(bin_dir):
    _exe(bin_dir, "claude", 'import json; print(json.dumps({"type": "result", "is_error": True, "subtype": "error", "result": "quota"}))')
    with pytest.raises(LLMError, match="quota"):
        ClaudeCodeLLM().complete_json(LLMRequest("C", "T", SCHEMA, timeout_s=10))
    _exe(bin_dir, "claude", "import time; time.sleep(30)")
    with pytest.raises(LLMError, match="timed out"):
        ClaudeCodeLLM().complete_json(LLMRequest("C", "T", SCHEMA, timeout_s=1))


def test_codex_call_reads_answer_file(bin_dir, tmp_path):
    log = tmp_path / "codex_args.json"
    _exe(bin_dir, "codex", f'''
import json, sys
args = sys.argv[1:]
json.dump({{"args": args, "stdin": sys.stdin.read()}}, open({str(log)!r}, "w"))
open(args[args.index("-o") + 1], "w").write(json.dumps({{"x": 3}}))
''')
    out = CodexLLM().complete_json(LLMRequest(shared_context="CASE", task="TASK", schema=SCHEMA,
                                              effort="low", timeout_s=10))
    assert out == {"x": 3}
    seen = json.loads(log.read_text())
    a = seen["args"]
    assert a[:2] == ["exec", "--ephemeral"] and a[a.index("-s") + 1] == "read-only"
    assert "--ignore-user-config" in a and 'web_search="disabled"' in a
    disabled = {a[i + 1] for i, x in enumerate(a) if x == "--disable"}
    assert {"shell_tool", "unified_exec", "browser_use", "computer_use", "plugins"} <= disabled
    assert 'model_reasoning_effort="low"' in a and a[-1] == "-"
    assert seen["stdin"].startswith("CASE") and "TASK" in seen["stdin"]


def test_codex_failure_is_an_llm_error(bin_dir):
    _exe(bin_dir, "codex", 'import sys; print("ERROR: model not supported", file=sys.stderr); sys.exit(1)')
    with pytest.raises(LLMError, match="not supported"):
        CodexLLM().complete_json(LLMRequest("C", "T", SCHEMA, timeout_s=10))


def test_all_backends_share_base_class_and_schema_and_removed_providers_fail(bin_dir, monkeypatch):
    from claimbot.llm import (
        AntigravityBackend,
        AnthropicBackend,
        ClaudeCodeBackend,
        CodexBackend,
        LLMBackend,
        VALUATION_SCHEMA,
        make_llm,
    )

    for cls in (AntigravityBackend, AnthropicBackend, ClaudeCodeBackend, CodexBackend):
        assert issubclass(cls, LLMBackend)

    # Default LLMRequest uses the shared VALUATION_SCHEMA
    req = LLMRequest(shared_context="CTX", task="TASK")
    assert req.schema is VALUATION_SCHEMA

    # Swapping models/effort via constructor works uniformly
    _exe(bin_dir, "claude", 'import json; print(json.dumps({"type":"result","is_error":False,"structured_output":{"lines":[]}}))')
    cc = ClaudeCodeBackend(model="sonnet", effort="medium")
    assert cc.model == "sonnet" and cc.effort == "medium"
    assert cc.ask("TASK", shared_context="CTX") == {"lines": []}

    # Fake and OpenAI API backends are removed
    for removed in ("fake", "openai"):
        with pytest.raises(LLMError, match="unknown provider"):
            make_llm(removed)
