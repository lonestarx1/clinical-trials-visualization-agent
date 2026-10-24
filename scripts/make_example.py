"""Ask one question in live mode, draw its chart, and write examples/NNN-slug.md.

usage: uv run --project backend --with matplotlib python scripts/make_example.py N "question" [base url]

The chart is drawn from the response's own `visualization` (type, encoding, data), so it shows
exactly what the API returned. It goes to examples/charts/NNN.png, linked from the Markdown.
"""

import json
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402

ARGS = [a for a in sys.argv[1:] if a != "--data-only"]
DATA_ONLY = "--data-only" in sys.argv  # only the web page's JSON (a stored answer, no new .md)
N, QUESTION = int(ARGS[0]), ARGS[1]
BASE = ARGS[2] if len(ARGS) > 2 else "https://api.cheiron.engineeradriel.com"
WEB = "https://trials.cheiron.engineeradriel.com"
OUT = Path(__file__).resolve().parent.parent / "examples"
COLORS = ["#2563eb", "#e0a030", "#16a34a", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]


def call(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data, {"Content-Type": "application/json"}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return e.code, {"error": raw.decode(errors="replace")[:500]}


def ask() -> tuple[int, dict[str, Any], float, bool]:
    t = time.time()
    status, body = call("POST", "/v1/query", {"query": QUESTION, "mode": "live"})
    job = status == 202
    while status == 202 or (job and body.get("status") in ("pending", "running")):
        time.sleep(3)
        status, body = call("GET", f"/v1/jobs/{body.get('job_id') or body.get('id')}")
        if body.get("status") not in ("pending", "running"):
            body = body.get("result") or {"status": body.get("status"), "error": body.get("error")}
            break
    return status, body, time.time() - t, job


def fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.1f}"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    return str(v).replace("|", "\\|")


def field(enc: dict[str, Any], ch: str) -> str | None:
    c = enc.get(ch)
    return c["field"] if c else None


def label(enc: dict[str, Any], ch: str) -> str:
    c = enc.get(ch) or {}
    unit = f" ({c['unit']})" if c.get("unit") and c["unit"] not in c.get("label", "") else ""
    return f"{c.get('label', ch)}{unit}"


def draw(v: dict[str, Any], png: Path) -> None:
    kind, enc, data = v["type"], v["encoding"], v["data"]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    title = "\n".join(textwrap.wrap(v["title"], 90))
    if kind == "metric":
        value = data[0][field(enc, "value")] if data else 0
        ax.axis("off")
        ax.text(0.5, 0.55, fmt(value), ha="center", va="center", fontsize=60, weight="bold",
                color=COLORS[0])
        ax.text(0.5, 0.25, label(enc, "value"), ha="center", fontsize=16, color="#555")
    elif kind == "network_graph":
        g = nx.Graph()
        for n in data["nodes"]:
            g.add_node(n["id"], **n)
        for e in data["edges"]:
            g.add_edge(e["source"], e["target"], weight=e["weight"])
        pos = nx.spring_layout(g, seed=7, k=1.2 / max(len(g), 1) ** 0.5, weight="weight")
        top = max((n["weight"] for n in data["nodes"]), default=1)
        topw = max((e["weight"] for e in data["edges"]), default=1)
        nx.draw_networkx_edges(g, pos, ax=ax, alpha=0.35, edge_color="#888",
                               width=[0.5 + 4 * g[a][b]["weight"] / topw for a, b in g.edges])
        nx.draw_networkx_nodes(g, pos, ax=ax, node_size=[60 + 900 * g.nodes[n]["weight"] / top
                                                         for n in g.nodes],
                               node_color=[COLORS[int(g.nodes[n].get("community") or 0) % 8]
                                           for n in g.nodes], alpha=0.85)
        nx.draw_networkx_labels(g, pos, ax=ax, font_size=7,
                                labels={n: g.nodes[n]["label"][:24] for n in g.nodes})
        ax.axis("off")
    elif kind == "scatter_plot":
        x, y = field(enc, "x"), field(enc, "y")
        ax.scatter([d[x] for d in data], [d[y] for d in data], s=14, alpha=0.6, color=COLORS[0])
        ax.set_xlabel(label(enc, "x"))
        ax.set_ylabel(label(enc, "y"))
    else:  # bar, grouped bar, time series, histogram
        x, y, color = field(enc, "x"), field(enc, "y"), field(enc, "color")
        groups = list(dict.fromkeys(d[color] for d in data)) if color else [None]
        cats = list(dict.fromkeys(d[x] for d in data))
        if kind == "histogram":
            widths = [d["bin_end"] - d[x] for d in data if d.get("bin_end") is not None]
            for d in data:  # the last bin can be open-ended ("500+"): draw it one width wide
                end = d["bin_end"] if d.get("bin_end") is not None else d[x] + max(widths or [1])
                ax.bar(d[x], d[y], width=end - d[x], align="edge", color=COLORS[0],
                       edgecolor="white")
        elif kind == "time_series":
            for i, gname in enumerate(groups):
                pts = sorted((d[x], d[y]) for d in data if not color or d[color] == gname)
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", ms=3,
                        color=COLORS[i % 8], label=gname)
        else:
            width = 0.8 / len(groups)
            for i, gname in enumerate(groups):
                vals = {d[x]: d[y] for d in data if not color or d[color] == gname}
                ax.bar([j + i * width - 0.4 + width / 2 for j in range(len(cats))],
                       [vals.get(c, 0) for c in cats], width=width, color=COLORS[i % 8],
                       label=gname)
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels([str(c)[:28] for c in cats], rotation=40 if len(cats) > 5 else 0,
                               ha="right" if len(cats) > 5 else "center", fontsize=8)
        if color:
            ax.legend(fontsize=8, title=label(enc, "color"))
        ax.set_xlabel(label(enc, "x"))
        ax.set_ylabel(label(enc, "y"))
        ax.grid(axis="y", alpha=0.3)
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(png, dpi=110)
    plt.close(fig)


def table(v: dict[str, Any]) -> list[str]:
    enc, data = v["encoding"], v["data"]
    if v["type"] == "network_graph":
        nodes = sorted(data["nodes"], key=lambda n: -n["weight"])[:15]
        edges = sorted(data["edges"], key=lambda e: -e["weight"])[:15]
        name = {n["id"]: n["label"] for n in data["nodes"]}
        lines = ["**Largest nodes** (trials)", "", "| Entity | Type | Trials | Links |",
                 "|---|---|---:|---:|"]
        lines += [f"| {fmt(n['label'])} | {n.get('type', '')} | {fmt(n['weight'])} | "
                  f"{fmt(n.get('degree', ''))} |" for n in nodes]
        lines += ["", "**Strongest links** (shared trials)", "", "| From | To | Shared trials |",
                  "|---|---|---:|"]
        lines += [f"| {fmt(name.get(e['source'], e['source']))} | "
                  f"{fmt(name.get(e['target'], e['target']))} | {fmt(e['weight'])} |"
                  for e in edges]
        return lines
    cols = [c for c in ("x", "color", "y", "value") if c in enc]
    keys = [enc[c]["field"] for c in cols]
    if v["type"] == "histogram" and data and "bin_end" in data[0]:
        keys.insert(1, "bin_end")
        cols.insert(1, "to")
    y = enc.get("y", enc.get("value", {})).get("field")
    extra = [k for k in ("estimated_count", "citation_count") if data and k in data[0]
             and k not in keys and any(d.get(k) != d.get(y) for d in data)]
    head = [label(enc, c) if c in enc else c for c in cols] + extra
    rows = data[:40]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(fmt(d.get(k, "")) for k in keys + extra) + " |" for d in rows]
    if len(data) > 40:
        lines.append(f"\n_{len(data) - 40} more rows in the API response._")
    return lines


def sample(v: dict[str, Any]) -> list[str]:
    data = v["data"]
    points = [*data["nodes"], *data["edges"]] if isinstance(data, dict) else data
    out = []
    for p in points:
        for c in p.get("citations", [])[:1]:
            out.append(f"- `{p['key']}`: [{c['nct_id']}]({c['url']}) {c['title'][:110]}")
        if len(out) >= 5:
            break
    return out


def save_data(body: dict[str, Any], meta: dict[str, Any], v: dict[str, Any] | None) -> None:
    """examples/data/NNN.json for the web app's Examples page: the chart spec, without citations."""
    viz = None
    if v:
        strip = lambda p: {k: x for k, x in p.items() if k != "citations"}  # noqa: E731
        data = v["data"]
        viz = v | {"data": {k: [strip(p) for p in data[k]] for k in data}
                   if isinstance(data, dict) else [strip(p) for p in data]}
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    record = {"n": N, "question": QUESTION, "status": body.get("status") or "rejected",
              "visualization": viz, "unique_trials": meta.get("unique_trials"),
              "reason": (meta.get("details") or {}).get("reason") or err.get("message"),
              "suggestion": (meta.get("details") or {}).get("suggestion")}
    OUT.joinpath("data").mkdir(parents=True, exist_ok=True)
    OUT.joinpath("data", f"{N:03d}.json").write_text(json.dumps(record, separators=(",", ":")))


def main() -> None:
    OUT.joinpath("charts").mkdir(parents=True, exist_ok=True)
    http, body, seconds, job = ask()
    meta = body.get("meta") or {}
    v = body.get("visualization")
    save_data(body, meta, v)
    if DATA_ONLY:
        print(f"data/{N:03d}.json: {body.get('status') or 'rejected'}")
        return
    slug = re.sub(r"[^a-z0-9]+", "-", QUESTION.lower()).strip("-")[:60].strip("-")
    md = OUT / f"{N:03d}-{slug}.md"
    for old in OUT.glob(f"{N:03d}-*.md"):
        old.unlink()
    link = f"{WEB}/?{urllib.parse.urlencode({'q': QUESTION, 'mode': 'live'})}"
    lines = [f"# {N:03d}. {QUESTION}", "", f"**Question:** {QUESTION}", "",
             f"Asked in **live** mode against `{BASE}` on "
             f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC. "
             f"[Open in the web app]({link}).", "", "## Answer", "",
             f"- **Status:** `{body.get('status') or 'rejected'}` (HTTP {http}"
             f"{', ran as a background job' if job else ''})",
             f"- **Time to answer:** {seconds:.1f} s"
             + (" (a stored answer)" if (meta.get("cache") or {}).get("result") == "hit" else "")]
    if v:
        lines.append(f"- **Title:** {v['title']}")
        lines.append(f"- **Chart:** `{v['type']}`")
    it = meta.get("interpretation") or {}
    if it:
        lines.append("- **Interpretation:** " + ", ".join(
            f"{k} `{it[k]}`" for k in ("intent", "dimension", "dimension_2", "measure")
            if it.get(k)))
    if meta.get("filters"):
        lines.append(f"- **Filters:** `{json.dumps(meta['filters'])}`")
    if meta.get("unique_trials") is not None:
        lines.append(f"- **Trials counted:** {fmt(meta['unique_trials'])}")
    if meta.get("data_timestamp"):
        lines.append(f"- **ClinicalTrials.gov data of:** {meta['data_timestamp']}")
    if isinstance(body.get("error"), dict):  # a refusal before any plan, e.g. the input policy
        err = body["error"]
        lines.append(f"- **Error:** `{err.get('code')}`: {err.get('message')}")
    elif body.get("error"):
        lines.append(f"- **Error:** {body['error']}")
    if v:
        png = OUT / "charts" / f"{N:03d}.png"
        draw(v, png)
        lines += ["", "## Chart", "", f"![{v['title']}](charts/{png.name})", "", "## Data", ""]
        lines += table(v)
    else:
        details = meta.get("details") or {}
        lines += ["", "## Why there is no chart", ""]
        if isinstance(body.get("error"), dict):
            details = {"code": body["error"].get("code"), "message": body["error"].get("message"),
                       **(body["error"].get("details") or {})}
        lines += [f"- **{k}:** {fmt(val)}" for k, val in details.items()] or ["- (no details)"]
    for name, key in (("Counting rule", "counting_rule"),):
        if meta.get(key):
            lines += ["", f"## {name}", "", meta[key]]
    for name, key in (("Assumptions", "assumptions"), ("Warnings", "warnings"),
                      ("Notes", "notes")):
        if meta.get(key):
            lines += ["", f"## {name}", ""] + [f"- {x}" for x in meta[key]]
    if meta.get("excluded"):
        lines += ["", "## Left out", ""] + [f"- {fmt(e['count'])} trials: {e['reason']}"
                                            for e in meta["excluded"]]
    if v and (s := sample(v)):
        lines += ["", "## Sample citations", ""] + s
    if meta.get("api_queries"):
        lines += ["", "## ClinicalTrials.gov queries", ""]
        lines += [f"- [{q.get('group') or 'search'}]({q['url']}): {fmt(q['total_count'])} trials"
                  for q in meta["api_queries"][:6]]
    if meta.get("timings_ms"):
        lines += ["", "## Timings (ms)", "", "`" + json.dumps(meta["timings_ms"]) + "`"]
    md.write_text("\n".join(lines) + "\n")
    print(f"{md.name}: {body.get('status') or 'rejected'} in {seconds:.1f}s"
          f"{' (' + v['type'] + ')' if v else ''}")


main()
