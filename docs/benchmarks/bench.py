"""Ask each question in fast mode, then live; record wall time, mode used and stage timings.

usage: python3 bench.py <questions file> <output jsonl> [base url]
"""
import json, sys, time, urllib.request, urllib.error

QFILE, OUT = sys.argv[1], sys.argv[2]
BASE = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"

def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data, {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def ask(q, mode, cpd):
    t = time.time()
    status, body = call("POST", "/v1/query", {"query": q, "mode": mode, "citations_per_datum": cpd})
    job = False
    if status == 202:  # a background job: poll until it finishes
        job = True
        while True:
            time.sleep(2)
            _, j = call("GET", f"/v1/jobs/{body['job_id']}")
            if j["status"] not in ("pending", "running"):
                body = j.get("result") or {"error": j.get("error"), "status": j["status"]}
                break
    meta = body.get("meta") or {}
    return {
        "mode_asked": mode, "seconds": round(time.time() - t, 2), "http": status, "job": job,
        "status": body.get("status"), "data_source": meta.get("data_source"),
        "unique_trials": meta.get("unique_trials"), "timings_ms": meta.get("timings_ms"),
        "fast_note": [n for n in meta.get("notes", []) if n.startswith("Fast mode")],
        "error": body.get("error"),
    }

with open(QFILE) as f, open(OUT, "w") as out:
    for q in (line.strip() for line in f if line.strip()):
        fast = ask(q, "fast", 4)   # fast first: it pays for planning; live then reuses the plan
        live = ask(q, "live", 3)   # a different citations_per_datum: no stored-answer reuse
        out.write(json.dumps({"question": q, "fast": fast, "live": live}) + "\n"); out.flush()
        print(f"{q[:60]:60s} fast {fast['seconds']:6.1f}s ({fast['data_source']}) live {live['seconds']:6.1f}s", flush=True)
