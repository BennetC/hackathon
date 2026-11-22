"""Push test/live results to FDN Bench (https://bench.159-195-78-137.sslip.io). Token: .bench_token (chmod 600)."""
import json, pathlib, urllib.request, urllib.error
HERE = pathlib.Path(__file__).resolve().parent
URL = "https://bench.159-195-78-137.sslip.io"

def _token():
    return (HERE / ".bench_token").read_text().strip()

def push(name, predictions, *, author="zorvink-claude", model="", description="", tags=None, timeout=20):
    """predictions: [{"game_id": g, "items": [{"index", "charge_price", "acceptance_limit"}], "latency_ms"?, "cost_usd"?, "metadata"?}]"""
    body = {"strategy_name": name, "author": author, "model": model, "description": description,
            "tags": tags or [], "predictions": predictions}
    req = urllib.request.Request(URL + "/api/runs", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:300]}")

def items(ab):
    return [{"index": int(l), "charge_price": round(float(v[0]), 2), "acceptance_limit": round(float(v[1]), 2)}
            for l, v in sorted(ab.items(), key=lambda kv: int(kv[0]))]
