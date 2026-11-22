"""Local Antigravity ACP backend for Gemini 4 Neon (zero external tools, inline images, warm sessions).

Uses `antigravity acp` (Agent Client Protocol stdio JSON-RPC server) rather than one-shot
CLI print invocations:
  - Native inline base64 `image` content blocks in `session/prompt` (`[{"type":"image",...}, {"type":"text",...}]`),
    delivering Daniil's exact `[image blocks..., text]` payload in ONE single turn with ZERO tool round-trips.
  - Persistent warm ACP worker process per named session (`neon-1`, `neon-2`, `neon-3`, `decider`),
    eliminating ~4s cold CLI startup per turn, with `session/load` resume across process restarts.
  - Strict zero-tools lockdown (mirroring Daniil's `--strict-mcp-config --tools ""`):
      1. Isolated `--gemini-dir` with empty `config/mcp_config.json` (`{"mcpServers":{}}`) so user
         global MCP servers (such as Warroom) are never loaded.
      2. Custom zero-tools agent (`claimbot-notools`, `tools: []`, `commandExecutionPolicy: off`,
         `mcpServers: []`) + `--include-default-customizations=false`.
      3. `settings.json` denying `command(*)`, `read_file(*)`, `write_file(*)`, `read_url(*)`,
         `execute_url(*)`, `mcp(*)`.
      4. Defense-in-depth: any `session/request_permission` RPC from the server is immediately
         cancelled/rejected by the client.
  - Exact Daniil image preprocessing (`prepare_daniil_image`: raw bytes <= 5 MB base64; else RGB
    `thumbnail((1568, 1568))`, JPEG quality 88; ALL photos sorted by path, no count limit).
  - Hard per-turn timeouts via process-group `SIGKILL` (`start_new_session=True`).
"""

from __future__ import annotations

import atexit
import base64
import json
import logging
import os
import re
import select
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from claimbot.llm.base import LLMBackend, LLMError, LLMRequest
from claimbot.preprocessing.images import prepare_daniil_image

log = logging.getLogger("claimbot.antigravity")

DEFAULT_MODEL = "gemini-4-neon-low"
DEFAULT_EFFORT = "low"

LOCKED_AGENT_NAME = "claimbot-notools"
LOCKED_APP_DATA_DIR = "claimbot-acp"

_LOCKED_AGENT_MD = (
    "---\n"
    f"name: {LOCKED_AGENT_NAME}\n"
    "description: Isolated zero-tools insurance claims valuation agent.\n"
    "tools: []\n"
    "mainAgent: true\n"
    "subagent: false\n"
    "commandExecutionPolicy: off\n"
    "mcpServers: []\n"
    "---\n"
    "You have NO tools. Never invoke any tool, command, file access, web search, or MCP server.\n"
    "Answer directly from the provided prompt and any inline attached images only.\n"
)

_LOCKED_SETTINGS = {
    "auth": {"type": "oauth-personal"},
    "permissions": {
        "deny": [
            "command(*)",
            "read_file(*)",
            "write_file(*)",
            "read_url(*)",
            "execute_url(*)",
            "mcp(*)",
        ]
    },
}


@dataclass(frozen=True)
class AntigravityTurnResult:
    conversation_id: str
    text: str
    structured_output: dict | None
    context_tokens: int
    usage: dict
    duration_s: float


def find_antigravity_bin() -> str:
    """Locate the Antigravity CLI/ACP binary (`agy` or T3's `antigravity-acp` binary).

    Never returns `/usr/bin/antigravity` or `/opt/Antigravity/antigravity` (Electron desktop GUI).
    """
    override = os.environ.get("CLAIMBOT_ANTIGRAVITY_BIN", "").strip()
    if override:
        p = Path(override)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        raise LLMError(f"CLAIMBOT_ANTIGRAVITY_BIN={override!r} is not an executable file")

    agy = shutil.which("agy")
    if agy:
        return agy

    t3_root = Path.home() / ".t3" / "tools" / "antigravity-acp"
    if t3_root.is_dir():
        candidates = [
            p for p in t3_root.glob("*/versions/*/antigravity")
            if p.is_file() and os.access(p, os.X_OK)
        ]
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return str(candidates[0])

    raise LLMError(
        "Antigravity CLI not found (checked CLAIMBOT_ANTIGRAVITY_BIN, `agy` on PATH, "
        "and ~/.t3/tools/antigravity-acp/*/versions/*/antigravity)"
    )


def normalize_model_slug(model: str | None, effort: str | None) -> tuple[str, str | None]:
    """Map (model, effort) onto Antigravity model slug (e.g. `gemini-4-neon-low`)."""
    m = (model or DEFAULT_MODEL).strip()
    e = (effort or "").strip().lower() or None
    tiers = ("low", "medium", "high", "xhigh")
    if any(m.endswith(f"-{t}") for t in tiers):
        return m, None
    if e in tiers and m in (
        "gemini-4-neon", "gemini-4-carbon", "gemini-4-argon",
        "gemini-4-hydrogen", "gemini-3.8-flash",
        "claude-opus-5-5", "claude-sonnet-5-5",
    ):
        return f"{m}-{e}", None
    return m, e


def prepare_isolated_gemini_dir(gemini_dir: Path) -> Path:
    """Create an isolated `--gemini-dir` with zero MCP servers and a zero-tools custom agent."""
    gdir = gemini_dir.resolve()
    (gdir / "config" / "agents" / LOCKED_AGENT_NAME).mkdir(parents=True, exist_ok=True)
    (gdir / LOCKED_APP_DATA_DIR).mkdir(parents=True, exist_ok=True)
    (gdir / "config" / "mcp_config.json").write_text('{"mcpServers":{}}\n', encoding="utf-8")
    (gdir / LOCKED_APP_DATA_DIR / "settings.json").write_text(
        json.dumps(_LOCKED_SETTINGS, indent=2) + "\n", encoding="utf-8"
    )
    (gdir / "config" / "agents" / LOCKED_AGENT_NAME / "agent.md").write_text(
        _LOCKED_AGENT_MD, encoding="utf-8"
    )
    return gdir


def extract_json_object(text: str) -> dict:
    """Parse a JSON object from model text, tolerating optional markdown fences."""
    s = (text or "").strip()
    if not s:
        raise LLMError("antigravity: empty response when JSON was expected")
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Strip ```json ... ``` fences if present
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    # Fallback: first `{` through last `}`
    lo, hi = s.find("{"), s.rfind("}")
    if lo != -1 and hi > lo:
        try:
            parsed = json.loads(s[lo:hi + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise LLMError(f"antigravity: invalid JSON output: {s[:240]!r}")


def _build_inline_image_blocks(images: list[Path]) -> list[dict]:
    """Encode ALL photos (sorted by path, no count limit) with Daniil's 5 MB / 1568 px / JPEG-88 rule."""
    blocks: list[dict] = []
    for photo in sorted(images, key=lambda p: str(p)):
        media_type, raw_bytes, _ = prepare_daniil_image(photo)
        blocks.append({
            "type": "image",
            "data": base64.standard_b64encode(raw_bytes).decode("ascii"),
            "mimeType": media_type,
        })
    return blocks


def _kill_proc_group(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                pass
    except Exception:
        pass
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


class _AcpWorker:
    """One persistent, locked-down `antigravity acp` stdio JSON-RPC worker process."""

    def __init__(self, bin_path: str, cwd: Path, gemini_dir: Path):
        self.bin_path = bin_path
        self.cwd = cwd.resolve()
        self.gemini_dir = prepare_isolated_gemini_dir(gemini_dir)
        self.proc: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = threading.Lock()
        self._read_buf = bytearray()
        self._loaded_sessions: set[str] = set()
        self._model_by_session: dict[str, str] = {}
        self._start()

    def _start(self) -> None:
        self.cwd.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.bin_path,
            "acp",
            "--gemini-dir", str(self.gemini_dir),
            "--app-data-dir", LOCKED_APP_DATA_DIR,
            "--agent", LOCKED_AGENT_NAME,
            "--include-default-customizations=false",
        ]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(self.cwd),
            env=dict(os.environ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
        self._read_buf.clear()
        self._loaded_sessions.clear()
        self._model_by_session.clear()
        self._rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
                "clientInfo": {"name": "claimbot-acp", "version": "1.0"},
            },
            timeout_s=20.0,
        )

    def _ensure_alive(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            _kill_proc_group(self.proc)
            self.proc = None
            self._start()

    def close(self) -> None:
        with self._lock:
            _kill_proc_group(self.proc)
            self.proc = None
            self._read_buf.clear()
            self._loaded_sessions.clear()
            self._model_by_session.clear()

    def _readline_with_timeout(self, deadline: float) -> str:
        assert self.proc is not None and self.proc.stdout is not None
        fd = self.proc.stdout.fileno()
        while True:
            nl = self._read_buf.find(b"\n")
            if nl != -1:
                line = bytes(self._read_buf[:nl + 1])
                del self._read_buf[:nl + 1]
                return line.decode("utf-8", errors="replace")
            rem = deadline - time.monotonic()
            if rem <= 0:
                raise TimeoutError("ACP RPC timed out")
            ready, _, _ = select.select([fd], [], [], rem)
            if not ready:
                raise TimeoutError("ACP RPC timed out")
            chunk = os.read(fd, 65536)
            if not chunk:
                if self._read_buf:
                    line = bytes(self._read_buf)
                    self._read_buf.clear()
                    return line.decode("utf-8", errors="replace")
                err_tail = ""
                if self.proc.stderr is not None:
                    try:
                        if select.select([self.proc.stderr.fileno()], [], [], 0.05)[0]:
                            err_tail = os.read(self.proc.stderr.fileno(), 600).decode("utf-8", errors="replace")
                    except Exception:
                        pass
                raise LLMError(f"antigravity acp exited unexpectedly: {err_tail[:300]!r}")
            self._read_buf.extend(chunk)

    def _send_json(self, obj: dict) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def _rpc(self, method: str, params: dict, *, timeout_s: float) -> tuple[dict, list[dict]]:
        self._req_id += 1
        my_id = self._req_id
        deadline = time.monotonic() + max(1.0, timeout_s)
        try:
            self._send_json({"jsonrpc": "2.0", "id": my_id, "method": method, "params": params})
        except BrokenPipeError as exc:
            raise LLMError(f"antigravity acp broken pipe on {method}") from exc

        updates: list[dict] = []
        while True:
            try:
                raw_line = self._readline_with_timeout(deadline)
            except TimeoutError:
                _kill_proc_group(self.proc)
                self.proc = None
                raise LLMError(f"antigravity acp: {method} timed out after {timeout_s:.1f}s")

            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if "id" in data and data["id"] == my_id:
                if "error" in data and data["error"] is not None:
                    raise LLMError(f"antigravity acp {method} error: {data['error']}")
                return data.get("result") or {}, updates

            # Defense-in-depth: reject ANY server->client request (e.g. session/request_permission)
            if "id" in data and "method" in data:
                log.warning("ACP worker rejecting unexpected server request %s", data.get("method"))
                options = (data.get("params") or {}).get("options") or []
                reject_id = next(
                    (o.get("optionId") for o in options if "reject" in str(o.get("kind", "")).lower()),
                    None,
                )
                outcome = (
                    {"outcome": "selected", "optionId": reject_id}
                    if reject_id
                    else {"outcome": "cancelled"}
                )
                self._send_json({"jsonrpc": "2.0", "id": data["id"], "result": {"outcome": outcome}})
                continue

            updates.append(data)

    def run_turn(
        self,
        prompt_text: str,
        *,
        images: list[Path] | None = None,
        conversation_id: str | None = None,
        model_slug: str = DEFAULT_MODEL,
        schema: dict | None = None,
        timeout_s: float = 40.0,
    ) -> AntigravityTurnResult:
        with self._lock:
            t0 = time.monotonic()
            self._ensure_alive()

            # Create or load the session on this warm worker
            if conversation_id:
                sid = conversation_id
                if sid not in self._loaded_sessions:
                    try:
                        self._rpc(
                            "session/load",
                            {"sessionId": sid, "cwd": str(self.cwd), "mcpServers": []},
                            timeout_s=min(20.0, timeout_s),
                        )
                        self._loaded_sessions.add(sid)
                    except LLMError as exc:
                        log.warning("session/load failed for %s (%s); creating new session", sid, exc)
                        res = self._rpc(
                            "session/new",
                            {"cwd": str(self.cwd), "mcpServers": []},
                            timeout_s=min(20.0, timeout_s),
                        )[0]
                        sid = str(res["sessionId"])
                        self._loaded_sessions.add(sid)
            else:
                res = self._rpc(
                    "session/new",
                    {"cwd": str(self.cwd), "mcpServers": []},
                    timeout_s=min(20.0, timeout_s),
                )[0]
                sid = str(res["sessionId"])
                self._loaded_sessions.add(sid)

            # Set model only when changed for this session
            if self._model_by_session.get(sid) != model_slug:
                self._rpc(
                    "session/set_model",
                    {"sessionId": sid, "modelId": model_slug},
                    timeout_s=min(10.0, timeout_s),
                )
                self._model_by_session[sid] = model_slug

            # Build inline content blocks: [image blocks..., text] (exact Daniil §2 & §5 order!)
            blocks: list[dict] = _build_inline_image_blocks(list(images or []))
            final_text = prompt_text
            if schema is not None:
                final_text = (
                    f"{prompt_text}\n\n"
                    "Return ONLY raw valid JSON matching this JSON Schema "
                    "(no markdown code fences, no extra prose, do not call any tools):\n"
                    f"{json.dumps(schema, separators=(',', ':'))}"
                )
            blocks.append({"type": "text", "text": final_text})

            rem_timeout = max(1.0, timeout_s - (time.monotonic() - t0))
            prompt_res, updates = self._rpc(
                "session/prompt",
                {"sessionId": sid, "prompt": blocks},
                timeout_s=rem_timeout,
            )

            chunks: list[str] = []
            for u in updates:
                upd = (u.get("params") or {}).get("update") or {}
                if upd.get("sessionUpdate") == "agent_message_chunk":
                    content = upd.get("content") or {}
                    if content.get("type") == "text":
                        chunks.append(str(content.get("text") or ""))

            response_text = "".join(chunks)
            structured: dict | None = None
            if schema is not None:
                structured = extract_json_object(response_text)

            raw_usage = prompt_res.get("usage") or {}
            in_tok = int(raw_usage.get("inputTokens") or 0)
            cached_tok = int(raw_usage.get("cachedReadTokens") or 0)
            cached_write = int(raw_usage.get("cachedWriteTokens") or 0)
            out_tok = int(raw_usage.get("outputTokens") or 0)
            thought_tok = int(raw_usage.get("thoughtTokens") or 0)
            ctx_tok = in_tok + cached_tok + cached_write

            return AntigravityTurnResult(
                conversation_id=sid,
                text=response_text,
                structured_output=structured,
                context_tokens=ctx_tok,
                usage={
                    "input": in_tok,
                    "cached_input": cached_tok,
                    "output": out_tok,
                    "thinking": thought_tok,
                },
                duration_s=time.monotonic() - t0,
            )


class AntigravityBackend(LLMBackend):
    """Antigravity ACP backend supporting warm persistent sessions and stateless one-shot calls."""

    name = "antigravity"
    default_model = DEFAULT_MODEL
    default_effort = DEFAULT_EFFORT

    def __init__(
        self,
        model: str | None = None,
        effort: str | None = None,
        *,
        bin_path: str | None = None,
    ):
        super().__init__(model=model, effort=effort)
        self.bin = bin_path or find_antigravity_bin()
        self._workers: dict[str, _AcpWorker] = {}
        atexit.register(self.close)

    def _add_usage(self, usage: dict) -> None:
        self._record_usage(
            input=usage.get("input"),
            cached_input=usage.get("cached_input"),
            output=usage.get("output"),
        )

    def _get_worker(self, session_key: str, cwd: Path, gemini_dir: Path) -> _AcpWorker:
        with self._lock:
            worker = self._workers.get(session_key)
            if worker is None:
                worker = _AcpWorker(self.bin, cwd, gemini_dir)
                self._workers[session_key] = worker
            return worker

    def close(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.close()

    def run_session_turn(
        self,
        prompt: str,
        *,
        cwd: Path,
        conversation_id: str | None = None,
        model: str | None = DEFAULT_MODEL,
        effort: str | None = DEFAULT_EFFORT,
        schema: dict | None = None,
        timeout_s: float = 40.0,
        images: list[Path] | None = None,
        session_key: str | None = None,
        gemini_dir: Path | None = None,
    ) -> AntigravityTurnResult:
        """Run one turn on a warm persistent ACP worker (or transient worker if stateless)."""
        model_slug, _ = normalize_model_slug(model, effort)

        if session_key:
            gdir = gemini_dir or (cwd.resolve().parent / "acp_gemini")
            worker = self._get_worker(session_key, cwd, gdir)
            res = worker.run_turn(
                prompt,
                images=images,
                conversation_id=conversation_id,
                model_slug=model_slug,
                schema=schema,
                timeout_s=timeout_s,
            )
            self._add_usage(res.usage)
            return res

        # Stateless transient worker (closed immediately after turn)
        with tempfile.TemporaryDirectory(prefix="claimbot-acp-tmp-") as tmp:
            tmp_path = Path(tmp)
            worker = _AcpWorker(self.bin, cwd, gemini_dir or (tmp_path / "gemini"))
            try:
                res = worker.run_turn(
                    prompt,
                    images=images,
                    conversation_id=conversation_id,
                    model_slug=model_slug,
                    schema=schema,
                    timeout_s=timeout_s,
                )
            finally:
                worker.close()
        self._add_usage(res.usage)
        return res

    def compact_session(
        self,
        conversation_id: str,
        compact_prompt: str,
        *,
        cwd: Path,
        model: str | None = DEFAULT_MODEL,
        effort: str | None = DEFAULT_EFFORT,
        timeout_s: float = 120.0,
        session_key: str | None = None,
        gemini_dir: Path | None = None,
    ) -> AntigravityTurnResult:
        """Send a `/compact ...` turn to an existing persistent ACP session."""
        return self.run_session_turn(
            compact_prompt,
            cwd=cwd,
            conversation_id=conversation_id,
            model=model,
            effort=effort,
            schema=None,
            timeout_s=timeout_s,
            images=None,
            session_key=session_key,
            gemini_dir=gemini_dir,
        )

    def complete_json(self, req: LLMRequest) -> dict:
        """Stateless one-shot JSON call compatible with `LLMBackend`."""
        with tempfile.TemporaryDirectory(prefix="claimbot-acp-") as tmp:
            tmp_path = Path(tmp)
            prompt = (
                f"{req.shared_context}\n\n=== TASK ===\n{req.task}\n\n"
                "Answer directly with the requested JSON matching the schema."
            )
            res = self.run_session_turn(
                prompt,
                cwd=tmp_path / "work",
                conversation_id=None,
                model=self.resolve_model(req),
                effort=self.resolve_effort(req),
                schema=req.schema,
                timeout_s=req.timeout_s,
                images=list(req.images),
                session_key=None,
                gemini_dir=tmp_path / "gemini",
            )
        if res.structured_output is None:
            raise LLMError(f"antigravity: missing JSON output: {res.text[:200]!r}")
        return res.structured_output


AntigravityLLM = AntigravityBackend
