"""Copy the saved example answers into the web app and write their index.

Usage: python3 scripts/build_examples.py [source_dir]   (default examples/data)
Reads NNN.json files, copies them to frontend/public/examples/, and writes
frontend/public/examples/index.json: one row per example (n, question, status, title),
sorted by n. Rerun it whenever examples are added; gaps in the numbering are fine.
"""

import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "data"
OUT = ROOT / "frontend" / "public" / "examples"


def main() -> None:
    files = sorted(p for p in SRC.glob("*.json") if re.fullmatch(r"\d{3}\.json", p.name))
    if not files:
        sys.exit(f"No NNN.json files in {SRC}")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    rows = []
    for path in files:
        example = json.loads(path.read_text())
        shutil.copyfile(path, OUT / path.name)
        viz = example.get("visualization")
        rows.append({
            "n": example["n"],
            "question": example["question"],
            "status": example["status"],
            "title": viz["title"] if viz else None,
        })
    rows.sort(key=lambda r: r["n"])
    (OUT / "index.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} examples -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
