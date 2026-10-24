"use client";

import { useRef, useState } from "react";
import { Chart, type ChartHandle } from "@/components/Chart";
import { DataTable } from "@/components/DataTable";
import type { Theme } from "@/lib/theme";
import type { Datum, QueryResponse } from "@/lib/types";

const n = (v: number) => v.toLocaleString("en-US");

function sentenceFilters(filters: Record<string, any>): string {
  const parts: string[] = [];
  const list = (v: unknown) => (Array.isArray(v) ? v.join(" or ") : String(v));
  if (filters.drugs) parts.push(`testing ${list(filters.drugs)}`);
  if (filters.conditions) parts.push(`for ${list(filters.conditions)}`);
  if (filters.sponsors) parts.push(`led by ${list(filters.sponsors)}`);
  if (filters.countries) parts.push(`with sites in ${list(filters.countries)}`);
  if (filters.phases) parts.push(`in ${list(filters.phases)}`);
  if (filters.statuses) parts.push(`with status ${list(filters.statuses).toLowerCase().replace(/_/g, " ")}`);
  if (filters.start_year_min || filters.start_year_max)
    parts.push(`started ${filters.start_year_min ?? "…"}–${filters.start_year_max ?? "now"}`);
  if (filters.groups) parts.push(`compared across ${filters.groups.map((g: any) => g.label).join(", ")}`);
  return parts.length ? `Trials ${parts.join(", ")}.` : "All registered trials.";
}

export function Answer({ response, theme, onSelect, onCopyLink }: {
  response: QueryResponse; theme: Theme; onSelect: (d: Datum) => void; onCopyLink: () => void;
}) {
  const viz = response.visualization!;
  const m = response.meta;
  const [view, setView] = useState<"chart" | "table">("chart");
  const [copied, setCopied] = useState(false);
  const chart = useRef<ChartHandle>(null);

  function download() {
    const url = chart.current?.toPng();
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${viz.title.replace(/[^\w]+/g, "-").toLowerCase().slice(0, 60)}.png`;
    a.click();
  }

  const excluded: { reason: string; count: number }[] = m.excluded ?? [];
  return (
    <article className="answer">
      <header className="answer-head">
        <h1>{viz.title}</h1>
        <p className="lede">{viz.summary}</p>
        <p className="facts">
          <span>{n(m.unique_trials ?? 0)} trials</span>
          {m.data_timestamp && <span>Registry data of {new Date(m.data_timestamp + "Z").toLocaleDateString("en-US", { dateStyle: "medium" })}</span>}
          {m.cache?.result === "hit" && <span>Saved answer, still current</span>}
        </p>
      </header>

      <div className="figure">
        <div className="figure-bar">
          <div className="segmented" role="tablist" aria-label="View">
            <button role="tab" aria-selected={view === "chart"} className={view === "chart" ? "on" : ""} onClick={() => setView("chart")}>Chart</button>
            <button role="tab" aria-selected={view === "table"} className={view === "table" ? "on" : ""} onClick={() => setView("table")}>Table</button>
          </div>
          <p className="muted small hint-click">{view === "chart" ? "Click any mark to see its trials" : "Every value, with its trials"}</p>
          <div className="figure-actions">
            {view === "chart" && viz.type !== "metric" && <button className="ghost" onClick={download}>Download PNG</button>}
            <button className="ghost" onClick={() => { onCopyLink(); setCopied(true); setTimeout(() => setCopied(false), 1600); }}>
              {copied ? "Link copied" : "Copy link"}
            </button>
          </div>
        </div>
        {view === "chart"
          ? <Chart ref={chart} viz={viz} theme={theme} onSelect={onSelect} />
          : <DataTable viz={viz} onSelect={onSelect} />}
        {(m.warnings ?? []).length > 0 && (
          <ul className="callouts">{m.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>
        )}
      </div>

      <section className="method" aria-labelledby="method-title">
        <h2 id="method-title">How this was answered</h2>
        <div className="method-grid">
          <div>
            <h3>What was counted</h3>
            <p>{sentenceFilters(m.filters ?? {})}</p>
            {m.counting_rule && <p>{m.counting_rule}{m.additive === false ? " A trial can appear in more than one bar, so the bars add up to more than the total." : ""}</p>}
            {(m.assumptions ?? []).length > 0 && (
              <>
                <h3>How the question was read</h3>
                <ul>{m.assumptions.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>
              </>
            )}
          </div>
          <div>
            <h3>Not counted</h3>
            {excluded.length
              ? <ul>{excluded.map((e, i) => <li key={i}>{n(e.count)} {e.count === 1 ? "trial" : "trials"}: {e.reason}</li>)}</ul>
              : <p>No matching trial was dropped for missing or out-of-range data.</p>}
            {(m.notes ?? []).length > 0 && <ul className="notes">{m.notes.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>}
            {m.network && (
              <p>The network keeps the {m.network.nodes} most connected of {n(m.network.nodes_before)} entities and links with at
                least {m.network.min_edge_weight} shared trial{m.network.min_edge_weight === 1 ? "" : "s"}; colours are clusters found by community detection.</p>
            )}
          </div>
          <div>
            <h3>Check it yourself</h3>
            <ul>
              {(m.api_queries ?? []).map((q: any, i: number) => (
                <li key={i}><a href={q.url} target="_blank" rel="noreferrer">
                  {q.group ? `${q.group}: ` : ""}the ClinicalTrials.gov query ({n(q.total_count)} trials)</a></li>
              ))}
            </ul>
            <p className="muted small">
              The AI chose the chart and wrote the title; all numbers were computed from the records.
              {m.usage?.cost_usd != null && ` AI cost: $${Number(m.usage.cost_usd).toFixed(4)}.`}
            </p>
          </div>
        </div>
        <details className="tech">
          <summary>Technical details</summary>
          <dl>
            <dt>Plan</dt><dd>{m.interpretation?.intent}, {m.interpretation?.chart_type?.replace(/_/g, " ")} by {m.interpretation?.dimension ?? "nothing"}{m.interpretation?.dimension_2 ? ` and ${m.interpretation.dimension_2}` : ""}, measuring {m.interpretation?.measure?.replace(/_/g, " ")}</dd>
            <dt>Agent</dt><dd>{m.planner?.steps ?? 0} planning steps; guard verdict {m.guard?.verdict}; narration {m.narration?.fallback ? "used the template" : `passed its checks (attempt ${m.narration?.attempts ?? 1})`}</dd>
            <dt>Models</dt><dd>{(m.usage?.models ?? []).join(", ") || "none"} ({m.usage?.llm_calls ?? 0} calls)</dd>
            <dt>Cache</dt><dd>plan {m.cache?.plan ?? "–"}, result {m.cache?.result ?? "–"}</dd>
            <dt>Timings</dt><dd>{Object.entries(m.timings_ms ?? {}).map(([k, v]) => `${k} ${n(v as number)} ms`).join(", ")}</dd>
            <dt>Result ID</dt><dd><code>{response.result_id ?? "–"}</code></dd>
            <dt>Trace ID</dt><dd><code>{m.trace_id}</code></dd>
          </dl>
        </details>
        <details className="tech">
          <summary>Response JSON</summary>
          <pre className="json">{JSON.stringify(response, null, 2)}</pre>
        </details>
      </section>
    </article>
  );
}
