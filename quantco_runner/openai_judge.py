"""Second judge: OpenAI GPT-6.2 Astra via the Responses API (persistent via previous_response_id). Key: .openai_key (600)."""
import json, pathlib, time, urllib.request, urllib.error
HERE = pathlib.Path(__file__).resolve().parent
MODEL = "gpt-6.2-astra"
def _key(): return (HERE / ".openai_key").read_text().strip()
def call(text, schema=None, prev=None, timeout=60, instructions=None):
    body = {"model": MODEL, "input": text}
    if prev: body["previous_response_id"] = prev
    if instructions: body["instructions"] = instructions
    if schema: body["text"] = {"format": {"type": "json_schema", "name": "decision", "schema": schema, "strict": True}}
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "dur": time.perf_counter() - t, "err": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"ok": False, "dur": time.perf_counter() - t, "cutoff": "timed out" in str(e).lower(), "err": f"{type(e).__name__}: {e}"}
    txt = out.get("output_text") or "".join(c.get("text", "") for o in out.get("output", []) if o.get("type") == "message" for c in o.get("content", []))
    res = {"ok": True, "dur": time.perf_counter() - t, "id": out.get("id"), "text": txt, "usage": out.get("usage")}
    if schema:
        try: res["structured"] = json.loads(txt)
        except Exception as e: res.update(ok=False, err=f"bad JSON: {e}: {txt[:200]}")
    return res
