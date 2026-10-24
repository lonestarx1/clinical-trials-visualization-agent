import type { QueryResponse } from "@/lib/types";

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (<><dt>{title}</dt><dd><ul>{items.map((t, i) => <li key={i}>{t}</li>)}</ul></dd></>);
}

export function MetaPanel({ response }: { response: QueryResponse }) {
  const m = response.meta;
  const usage = m.usage ?? {};
  return (
    <dl className="meta">
      {m.interpretation && (
        <>
          <dt>Interpretation</dt>
          <dd>
            {m.interpretation.intent} · {m.interpretation.chart_type} · {m.interpretation.dimension ?? "no dimension"}
            {m.interpretation.dimension_2 ? ` × ${m.interpretation.dimension_2}` : ""} · {m.interpretation.measure}
            <span className="muted"> (chart chosen by: {m.interpretation.chart_type_source})</span>
          </dd>
        </>
      )}
      {Object.keys(m.filters ?? {}).length > 0 && (<><dt>Filters applied</dt><dd><code>{JSON.stringify(m.filters)}</code></dd></>)}
      <List title="Assumptions" items={m.assumptions} />
      <List title="Warnings" items={m.warnings} />
      <List title="Notes" items={m.notes} />
      {m.counting_rule && (<><dt>Counting rule</dt><dd>{m.counting_rule} {m.additive === false && <span className="muted">(values don't add up to the total: a trial can count in several)</span>}</dd></>)}
      {m.unique_trials != null && (<><dt>Distinct trials</dt><dd>{m.unique_trials.toLocaleString()}</dd></>)}
      <List title="Excluded" items={(m.excluded ?? []).map((e: { reason: string; count: number }) => `${e.count.toLocaleString()}: ${e.reason}`)} />
      {m.network && (<><dt>Network pruning</dt><dd>{m.network.nodes_before} → {m.network.nodes} nodes, {m.network.edges_before} → {m.network.edges} links (min. {m.network.min_edge_weight} shared trials); {m.network.community_algorithm}</dd></>)}
      {m.api_queries?.length > 0 && (
        <>
          <dt>ClinicalTrials.gov queries</dt>
          <dd><ul>{m.api_queries.map((q: { group: string | null; url: string; total_count: number }, i: number) => (
            <li key={i}>{q.group ? `${q.group}: ` : ""}<a href={q.url} target="_blank" rel="noreferrer">{q.total_count.toLocaleString()} trials</a></li>
          ))}</ul></dd>
        </>
      )}
      {m.data_timestamp && (<><dt>Data version</dt><dd>{m.data_timestamp} (ClinicalTrials.gov)</dd></>)}
      {m.cache && (<><dt>Cache</dt><dd>plan {m.cache.plan}{m.cache.result ? `, result ${m.cache.result}` : ""}</dd></>)}
      <dt>AI usage</dt>
      <dd>
        {usage.llm_calls ?? 0} model calls ({(usage.models ?? []).join(", ")}), {usage.cost_usd != null ? `$${Number(usage.cost_usd).toFixed(4)}` : "cost unknown"}
        {m.planner && <span className="muted"> · planner steps: {m.planner.steps}</span>}
        {m.narration && <span className="muted"> · narration {m.narration.fallback ? "template fallback" : `attempts: ${m.narration.attempts}`}</span>}
      </dd>
      {m.timings_ms && (<><dt>Timings</dt><dd>{Object.entries(m.timings_ms).map(([k, v]) => `${k} ${v} ms`).join(" · ")}</dd></>)}
      {m.trace_id && (<><dt>Trace</dt><dd><code>{m.trace_id}</code></dd></>)}
    </dl>
  );
}
