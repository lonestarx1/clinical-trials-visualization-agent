"""Run the README example requests against a running API and save request + response.

Usage: python3 scripts/run_examples.py [base_url]   (default http://localhost:8000)
The outputs in docs/examples/ are produced by this script only, never edited by hand.
"""

import json
import pathlib
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "examples"

EXAMPLES = [
    ("1-drug-trend", {
        "query": "How has the number of trials for this drug changed per year since 2015?",
        "drug_name": "Pembrolizumab", "citations_per_datum": 3}),
    ("2-condition-phases", {
        "query": "How are breast cancer trials distributed across phases?", "citations_per_datum": 3}),
    ("3-drug-comparison", {
        "query": "Compare phases for trials involving pembrolizumab vs nivolumab.",
        "citations_per_datum": 3}),
    ("4-recruiting-countries", {
        "query": "Which countries have the most recruiting trials for lung cancer?",
        "citations_per_datum": 3}),
    ("5-enrollment-histogram", {
        "query": "What is the distribution of enrollment sizes for Phase 3 Alzheimer's disease trials?",
        "citations_per_datum": 3}),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in EXAMPLES:
        request = urllib.request.Request(
            f"{BASE}/v1/query", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        started = time.time()
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read())
        seconds = round(time.time() - started, 1)
        record = {"request": body, "http_status": 200, "seconds": seconds, "response": result}
        (OUT / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        viz = result.get("visualization") or {}
        print(f"{name}: {result['status']} {viz.get('type')} in {seconds}s - {viz.get('title')}")


if __name__ == "__main__":
    main()
