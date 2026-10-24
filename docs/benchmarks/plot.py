import glob, json, statistics, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

B = sys.argv[1]
rows = [json.loads(l) for f in sorted([*glob.glob(f"{B}/results/*.jsonl"), *glob.glob(f"{B}/results.jsonl")]) for l in open(f) if l.strip()]
cached = [r for r in rows if r["live"]["seconds"] < 1.5 and r["fast"]["seconds"] < 1.5]  # stored answers from earlier tests
rows = [r for r in rows if r not in cached]
rows.sort(key=lambda r: r["live"]["seconds"])
labels = [r["question"][:62] for r in rows]
live = [r["live"]["seconds"] for r in rows]
fast = [r["fast"]["seconds"] for r in rows]
fell_back = [r["fast"]["data_source"] != "fast" for r in rows]

fig, ax = plt.subplots(figsize=(11, 0.32 * len(rows) + 1.6))
y = range(len(rows))
ax.barh([i + 0.2 for i in y], live, height=0.4, color="#8a94a6", label="Live")
ax.barh([i - 0.2 for i in y], fast, height=0.4,
        color=["#e0a030" if fb else "#2563eb" for fb in fell_back], label="Fast")
ax.set_yticks(list(y)); ax.set_yticklabels(labels, fontsize=7)
ax.set_xscale("log"); ax.set_xlabel("Seconds to answer (log scale)")
both = [(l, f) for l, f, fb in zip(live, fast, fell_back) if not fb]
med_l = statistics.median(l for l, _ in both) if both else 0
med_f = statistics.median(f for _, f in both) if both else 0
ax.set_title(f"Live vs fast, {len(rows)} questions. Answered fast: {len(both)}; "
             f"median {med_l:.1f}s live vs {med_f:.1f}s fast", fontsize=10)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color="#8a94a6", label="Live"), Patch(color="#2563eb", label="Fast"),
                   Patch(color="#e0a030", label="Fast mode fell back to live")], loc="lower right", fontsize=8)
ax.grid(axis="x", alpha=0.3); fig.tight_layout()
fig.savefig(f"{B}/live-vs-fast.png", dpi=130)
speed = sorted(l / f for l, f in both if f > 0)
print(f"cached (excluded): {len(cached)}"); print(f"{len(rows)} questions; {len(both)} answered fast; fell back: {sum(fell_back)}")
print(f"median live {med_l:.1f}s, median fast {med_f:.1f}s, median speed-up {statistics.median(speed):.1f}x" if speed else "")
print(f"fast slower than live: {sum(1 for x in speed if x < 1)}; jobs live: {sum(r['live']['job'] for r in rows)}, fast: {sum(r['fast']['job'] for r in rows)}")
for r in rows:
    if r["fast"]["data_source"] != "fast": print("  fell back:", r["question"][:60], r["fast"]["fast_note"][:1], r["fast"].get("error"))
# Fast answers' own work, without calls to ClinicalTrials.gov (term listing, live count) and
# without the mirror read, which isn't timed apart from them: a best case for an offline fast mode.
local = [sum(t.get(k, 0) for k in ("plan", "aggregate", "narrate")) / 1000
         for r in rows if r["fast"]["data_source"] == "fast" for t in [r["fast"]["timings_ms"] or {}]]
if local:
    print(f"fast without network calls: median {statistics.median(local):.1f}s, max {max(local):.1f}s")
