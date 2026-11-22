"""Agents run through locally installed agent CLIs, on your own subscriptions.

    ClaudeCode(...)  -> `claude -p`      (Claude subscription; text + photos)
    Codex(...)       -> `codex exec`     (ChatGPT login; text + photos)

Each call is a fresh, isolated, one-shot process with NO tools and no external resources:
  Claude Code: --tools "" (no built-in tools, incl. web search/fetch), --strict-mcp-config
               (no MCP servers), --setting-sources "" (no user/project settings, hooks,
               plugins), --disable-slash-commands, --no-session-persistence.
  Codex:       --ignore-user-config (no MCP servers/plugins from ~/.codex/config.toml),
               web search disabled, shell/exec, browser, computer use, apps, plugins,
               multi-agent, image generation, hooks, skills and view_image features
               disabled, read-only sandbox, --ephemeral.
Both run in an empty temporary working directory, answer against a JSON schema, and a
hard timeout kills the whole process group. Photos are sent as base64 image data: in the
Claude message itself (stream-json), and via `codex exec -i`, which encodes the attached
file into the request (the model does not open files itself).
Case documents are untrusted, which is why the agents get nothing to act with.
"""


from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from claimbot.llm.base import LLMBackend, LLMError, LLMRequest

CODEX_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "unified_exec_tty", "apps", "browser_use",
    "browser_use_external", "browser_use_full_cdp_access", "in_app_browser", "computer_use",
    "image_generation", "multi_agent", "plugins", "remote_plugin", "hooks", "skill_search",
    "tool_suggest", "view_image", "goals", "sleep_tool", "code_mode_host",
)



def _run(cmd: list[str], stdin: str, cwd: Path, timeout_s: float, env: dict) -> tuple[int, str, str]:
    """Run a CLI in its own process group so a timeout kills it and all its children."""
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = proc.communicate(stdin, timeout=max(1.0, timeout_s))
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise LLMError(f"{cmd[0]}: timed out after {timeout_s:.0f}s")
    return proc.returncode, out, err


class ClaudeCodeBackend(LLMBackend):
    name = "claude_code"
    default_model = "opus"
    default_effort = "high"

    def __init__(self, model: str | None = None, effort: str | None = None):
        super().__init__(model=model, effort=effort)
        self.bin = shutil.which("claude")
        if not self.bin:
            raise LLMError("claude CLI not found on PATH (install Claude Code and log in)")

    def complete_json(self, req: LLMRequest) -> dict:
        from claimbot.preprocessing.images import encode_image

        model = self.resolve_model(req)
        effort = self.resolve_effort(req)
        content: list[dict] = []
        for path in req.images:
            media_type, data = encode_image(path)
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": data}})
        content.append({"type": "text", "text": req.task})
        message = json.dumps({"type": "user", "message": {"role": "user", "content": content}})
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}  # use the subscription
        with tempfile.TemporaryDirectory(prefix="claimbot-cc-") as tmp:
            sys_file = Path(tmp) / "system.txt"
            sys_file.write_text(req.shared_context)
            cmd = [self.bin, "-p", "--input-format", "stream-json",
                   "--output-format", "stream-json", "--verbose",
                   "--json-schema", json.dumps(req.schema),
                   "--tools", "", "--no-session-persistence", "--strict-mcp-config",
                   "--setting-sources", "", "--disable-slash-commands",
                   "--system-prompt-file", str(sys_file)]
            if model:
                cmd += ["--model", model]
            if effort:
                cmd += ["--effort", effort]
            code, out, err = _run(cmd, message + "\n", Path(tmp), req.timeout_s, env)
        results = []
        for line in out.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result":
                results.append(event)
        if not results:
            raise LLMError(f"claude: exit {code}, no result: {(err or out)[-300:]!r}")
        data = results[-1]
        if data.get("is_error") or data.get("structured_output") is None:
            raise LLMError(f"claude: {data.get('subtype')} {str(data.get('result'))[:300]!r}")
        u = data.get("usage") or {}
        self._record_usage(
            input=(u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                  + (u.get("cache_creation_input_tokens") or 0),
            cached_input=u.get("cache_read_input_tokens"),
            output=u.get("output_tokens"),
        )
        return data["structured_output"]


class CodexBackend(LLMBackend):
    name = "codex"
    default_model = None
    default_effort = "high"

    def __init__(self, model: str | None = None, effort: str | None = None):
        super().__init__(model=model, effort=effort)
        self.bin = shutil.which("codex")
        if not self.bin:
            raise LLMError("codex CLI not found on PATH (install Codex and `codex login`)")

    def complete_json(self, req: LLMRequest) -> dict:
        model = self.resolve_model(req)
        effort = self.resolve_effort(req)
        with tempfile.TemporaryDirectory(prefix="claimbot-codex-") as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "schema.json").write_text(json.dumps(req.schema))
            cmd = [self.bin, "exec", "--ephemeral", "--ignore-user-config",
                   "--skip-git-repo-check", "-s", "read-only", "-C", tmp,
                   "-c", 'web_search="disabled"',
                   "--output-schema", str(tmp_path / "schema.json"),
                   "-o", str(tmp_path / "answer.json")]
            for feature in CODEX_DISABLED_FEATURES:
                cmd += ["--disable", feature]
            if model:
                cmd += ["-m", model]
            if effort:
                cmd += ["-c", f'model_reasoning_effort="{effort}"']
            for i, img in enumerate(req.images):
                from claimbot.preprocessing.images import encode_image
                import base64
                _, data = encode_image(img)
                small = tmp_path / f"photo{i}.jpg"
                small.write_bytes(base64.standard_b64decode(data))
                cmd += ["-i", str(small)]
            cmd.append("-")  # prompt from stdin
            prompt = (f"{req.shared_context}\n\n=== TASK ===\n{req.task}\n\n"
                      "Answer directly with the JSON. You have no tools.")
            code, out, err = _run(cmd, prompt, tmp_path, req.timeout_s, dict(os.environ))
            answer = tmp_path / "answer.json"
            text = answer.read_text() if answer.exists() else ""
        if code != 0 or not text.strip():
            tail = (err or out).strip().splitlines()[-3:]
            raise LLMError(f"codex: exit {code}: {' | '.join(tail)[:300]}")
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"codex: invalid JSON: {text[:200]!r}") from exc
        self._record_usage()
        return result


ClaudeCodeLLM = ClaudeCodeBackend
CodexLLM = CodexBackend
