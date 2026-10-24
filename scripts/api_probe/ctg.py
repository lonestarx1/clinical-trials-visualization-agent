"""Polite ClinicalTrials.gov probe helper (stdlib only).

Every call is throttled (>= MIN_GAP seconds apart), logged to calls.jsonl,
and its raw body saved under OUT/raw/<name>.json for later inspection.
"""
import json, os, time, urllib.parse, urllib.request, urllib.error

BASE = "https://clinicaltrials.gov/api/v2"
OUT = os.environ.get("PROBE_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs", "api", "probe-data"))
MIN_GAP = 1.5
_last = [0.0]


def call(name, path, params=None, save=True):
    wait = MIN_GAP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    qs = urllib.parse.urlencode(params or {}, safe="|,[]:")
    url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
    t0 = time.time()
    status, body, headers = None, b"", {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=60) as r:
            status, body, headers = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        status, body, headers = e.code, e.read(), dict(e.headers)
    dt = time.time() - t0
    _last[0] = time.time()
    os.makedirs(f"{OUT}/raw", exist_ok=True)
    if save:
        with open(f"{OUT}/raw/{name}.json", "wb") as f:
            f.write(body)
    rec = {"name": name, "url": url, "status": status, "seconds": round(dt, 2), "bytes": len(body),
           "ratelimit_headers": {k: v for k, v in headers.items() if "rate" in k.lower() or "retry" in k.lower()}}
    with open(f"{OUT}/calls.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    try:
        data = json.loads(body)
    except Exception:
        data = body.decode("utf-8", "replace")
    return status, data, rec


def count(name, **params):
    """Total matching studies for a search (1 tiny page)."""
    p = {"countTotal": "true", "pageSize": 1, "fields": "NCTId", **params}
    status, data, rec = call(name, "/studies", p, save=False)
    total = data.get("totalCount") if isinstance(data, dict) else None
    return status, total, rec, data


def fetch_all(name, max_pages=20, **params):
    """Fetch all pages (pageSize 1000) for a search; returns list of studies."""
    studies, token, page = [], None, 0
    while page < max_pages:
        p = {"pageSize": 1000, **params}
        if page == 0:
            p["countTotal"] = "true"
        if token:
            p["pageToken"] = token
        status, data, rec = call(f"{name}_p{page}", "/studies", p, save=False)
        if status != 200:
            raise RuntimeError(f"{status}: {str(data)[:300]}")
        studies += data.get("studies", [])
        token = data.get("nextPageToken")
        page += 1
        if not token:
            break
    with open(f"{OUT}/raw/{name}.json", "w") as f:
        json.dump(studies, f)
    return studies, page, token
