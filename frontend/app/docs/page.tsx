// The developer guide for the public API, written by hand and checked against the backend code
// (backend/app/schemas, backend/app/api) and the recorded responses in docs/examples.
import type { Metadata } from "next";
import { CodeBlock } from "@/components/CodeBlock";
import { DocsTopbar } from "@/components/DocsTopbar";
import { curl, publicApiUrl } from "@/lib/docs";

// PUBLIC_API_URL is a runtime setting (docker-compose, k8s): read it per request, not at build.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "API docs · Clinical Trials Explorer",
  description: "How to call the Clinical Trials Explorer API: turn a question about ClinicalTrials.gov into a chart spec with citations.",
};

const SECTIONS = [
  { id: "overview", title: "Overview" },
  { id: "quick-start", title: "Quick start" },
  { id: "request", title: "The request" },
  { id: "response", title: "The response" },
  { id: "statuses-errors", title: "Statuses and errors" },
  { id: "jobs", title: "Background jobs" },
  { id: "citations", title: "Citations paging" },
  { id: "options", title: "Options" },
  { id: "limits", title: "Limits" },
  { id: "reference", title: "Interactive reference" },
] as const;

const QUICK_BODY = { query: "How are breast cancer trials distributed across phases?", citations_per_datum: 3 };

// docs/examples/2-condition-phases.json, trimmed: 1 of 9 data points, 1 of 3 citations, part of meta.
const QUICK_RESPONSE = `{
  "schema_version": "2.0",
  "result_id": "d70db059-8f32-49a2-9fdc-231f5e3fd056",
  "status": "ok",
  "visualization": {
    "type": "bar_chart",
    "title": "ClinicalTrials.gov breast cancer trials by phase",
    "encoding": {
      "x": { "field": "phase", "type": "ordinal", "label": "Phase",
             "unit": null, "sort": "natural", "time_unit": null },
      "y": { "field": "trial_count", "type": "quantitative", "label": "Number of trials",
             "unit": "trials", "sort": null, "time_unit": null }
    },
    "data": [
      {
        "key": "PHASE1",
        "phase": "Phase 1",
        "trial_count": 1619,
        "citation_count": 1619,
        "citations": [
          {
            "nct_id": "NCT07454668",
            "url": "https://clinicaltrials.gov/study/NCT07454668",
            "title": "Trastuzumab Deruxtecan + Stereotactic Radiosurgery (SRS) in HER2+ Breast Cancer Brain Metastases",
            "evidence": [{ "field": "protocolSection.designModule.phases[0]", "excerpt": "PHASE1" }]
          }
        ],
        "citations_truncated": true
      }
    ]
  },
  "meta": {
    "interpretation": { "intent": "distribution", "chart_type": "bar_chart", "dimension": "phase",
                        "dimension_2": null, "measure": "trial_count", "chart_type_source": "ai" },
    "filters": { "conditions": ["breast cancer"] },
    "assumptions": ["Interpreting 'breast cancer trials' as trials with condition 'breast cancer'."],
    "warnings": [],
    "notes": [],
    "counting_rule": "Each trial is counted once; trials with two phases get a combined bucket (e.g. Phase 2/Phase 3).",
    "additive": true,
    "unique_trials": 16765,
    "excluded": [],
    "api_queries": [
      { "group": null, "url": "https://clinicaltrials.gov/api/v2/studies?query.cond=%22breast+cancer%22", "total_count": 16765 }
    ],
    "data_timestamp": "2026-10-23T09:00:04",
    "trace_id": "f99e189b-ed92-498b-909d-51252c63d1cd"
  }
}`;

const STRUCTURED_BODY = {
  query: "Compare phases for these drugs",
  compare: [
    { label: "Pembrolizumab", drug_name: "pembrolizumab" },
    { label: "Nivolumab", drug_name: "nivolumab" },
  ],
  status: ["RECRUITING"],
  start_year: 2018,
};

// docs/examples/5-drug-network.json: the encoding (unit, sort, time_unit cut) and the first node and edge.
const NETWORK_SAMPLE = `"encoding": {
  "node_id":     { "field": "id", "type": "nominal", "label": "Entity" },
  "node_label":  { "field": "label", "type": "nominal", "label": "Name" },
  "node_size":   { "field": "weight", "type": "quantitative", "label": "Trials" },
  "node_color":  { "field": "community", "type": "nominal", "label": "Community" },
  "edge_source": { "field": "source", "type": "nominal", "label": "From" },
  "edge_target": { "field": "target", "type": "nominal", "label": "To" },
  "edge_width":  { "field": "weight", "type": "quantitative", "label": "Shared trials" }
},
"data": {
  "nodes": [
    {
      "key": "drug:pembrolizumab", "id": "drug:pembrolizumab", "label": "pembrolizumab",
      "type": "drug", "weight": 250, "degree": 19, "community": 2, "is_query_entity": false,
      "citation_count": 250, "citations": [...], "citations_truncated": true
    }
  ],
  "edges": [
    {
      "key": "drug:ipilimumab|drug:nivolumab", "source": "drug:ipilimumab", "target": "drug:nivolumab",
      "weight": 122, "jaccard": 0.3873,
      "citation_count": 122, "citations": [...], "citations_truncated": true
    }
  ]
}`;

const RENDER_SAMPLE = `const { type, encoding, data } = response.visualization;
const x = encoding.x.field;   // "phase": never hard-code "phase" or "trial_count"
const y = encoding.y.field;   // "trial_count"
const bars = data.map((d) => ({ label: d[x], value: d[y], key: d.key }));
// Axis titles: encoding.x.label, encoding.y.label (+ encoding.y.unit).
// Order: keep the order of data (it is already sorted as meta.sort says).`;

const ERROR_SAMPLE = `{
  "error": {
    "code": "invalid_request",
    "message": "The request is not valid.",
    "details": [{ "loc": ["body", "foo"], "msg": "Extra inputs are not permitted" }],
    "trace_id": "58df5557-da79-4916-a112-8de8098a859d"
  }
}`;

const CITATIONS_META_SAMPLE = `// asked for full, got full
{ "requested": "full", "applied": "full", "per_datum": 5, "reason": null }

// asked for full on a broad question: too many to inline
{ "requested": "full", "applied": "sample", "per_datum": 5,
  "reason": "2,000 citation limit exceeded (17,450 contributing trial references); page through them with the citations endpoint" }`;

const ACCEPTED_SAMPLE = `HTTP/1.1 202 Accepted

{
  "job_id": "5b0d7c3e-…",
  "status": "pending",
  "poll_url": "/v1/jobs/5b0d7c3e-…",
  "estimated_seconds": 240
}`;

const JOB_SAMPLE = `{
  "job_id": "5b0d7c3e-…",
  "status": "running",
  "progress": { "stage": "retrieve", "pages_done": 12, "pages_total": 40 },
  "estimated_seconds": 240,
  "result": null,
  "error": null
}`;

const CANCELLED_SAMPLE = `{
  "job_id": "5b0d7c3e-…",
  "status": "cancelled",
  "progress": { "stage": "retrieve", "pages_done": 12, "pages_total": 40 },
  "estimated_seconds": 240,
  "result": null,
  "error": {
    "code": "cancelled",
    "message": "This job was cancelled.",
    "details": null,
    "trace_id": "…"
  }
}`;

const CITATIONS_SAMPLE = `{
  "result_id": "d70db059-8f32-49a2-9fdc-231f5e3fd056",
  "datum": "PHASE1",
  "label": "Phase 1",
  "citation_count": 1619,
  "citations": [
    {
      "rank": 0,
      "nct_id": "NCT07454668",
      "url": "https://clinicaltrials.gov/study/NCT07454668",
      "title": "Trastuzumab Deruxtecan + Stereotactic Radiosurgery (SRS) in HER2+ Breast Cancer Brain Metastases",
      "evidence": [{ "field": "protocolSection.designModule.phases[0]", "excerpt": "PHASE1" }]
    }
  ],
  "next_cursor": 50
}`;

const OPTIONS_SAMPLE = `{
  "dimensions": [
    { "key": "phase", "label": "Phase", "kind": "…", "multi_valued": false, "counting_rule": "…",
      "values": [{ "value": "PHASE1", "label": "Phase 1" }, …] },
    …
  ],
  "measures": [{ "key": "trial_count", "label": "…", "unit": "…" }, …],
  "chart_types": [{ "key": "bar_chart" }, …],
  "filters": {
    "trial_phase": [{ "value": "PHASE1", "label": "Phase 1" }, …],
    "status": [{ "value": "RECRUITING", "label": "Recruiting" }, …],
    "country": ["Afghanistan", …]
  }
}`;

type Row = [string, string, string, React.ReactNode];

const REQUEST_FIELDS: Row[] = [
  ["query", "string (required)", "none", <>The question in plain English, 1 to 1,000 characters after trimming.</>],
  ["drug_name", "string or string[]", "[]", <>Drugs to filter on. Several values mean any of them (OR). Up to 10 terms of up to 200 characters; the same applies to the next three fields.</>],
  ["condition", "string or string[]", "[]", <>Conditions or diseases.</>],
  ["sponsor", "string or string[]", "[]", <>Sponsor organisations (see <code>sponsor_role</code>).</>],
  ["country", "string or string[]", "[]", <>Countries with at least one trial site.</>],
  ["trial_phase", "string[]", "[]", <>Phases: <code>EARLY_PHASE1</code>, <code>PHASE1</code> to <code>PHASE4</code>, <code>NA</code>. Labels such as <code>&quot;Phase 3&quot;</code> are accepted too (case and punctuation are ignored).</>],
  ["status", "string[]", "[]", <>Overall status codes such as <code>RECRUITING</code> or <code>COMPLETED</code>, or their labels (<code>&quot;Recruiting&quot;</code>). The full list is in <a href="#options">/v1/options</a>.</>],
  ["start_year", "integer or null", "null", <>Earliest start year, 1900 to 10 years from now.</>],
  ["end_year", "integer or null", "null", <>Latest start year. Must not be before <code>start_year</code>.</>],
  ["compare", "object[]", "[]", <>2 to 4 groups to compare, each <code>{"{"} label, drug_name?, condition?, sponsor?, country? {"}"}</code>. Labels (1 to 100 characters) must be unique, and each group needs at least one entity.</>],
  ["chart_type", "string or null", "null", <>Force a chart: <code>bar_chart</code>, <code>grouped_bar_chart</code>, <code>time_series</code>, <code>histogram</code>, <code>scatter_plot</code>, <code>network_graph</code> or <code>metric</code>. If it can&apos;t show the question, the answer is <code>could_not_interpret</code>.</>],
  ["top_n", "integer or null", "null", <>Keep only the top N categories (1 to 50).</>],
  ["match_mode", "\"strict\" | \"broad\"", "\"strict\"", <>How drugs and conditions match. <code>strict</code> uses the intervention and condition fields (with synonyms); <code>broad</code> also matches titles, keywords and descriptions.</>],
  ["sponsor_role", "\"lead\" | \"any\"", "\"lead\"", <><code>lead</code>: the lead sponsor only. <code>any</code>: lead sponsor or collaborator.</>],
  ["citations", "\"sample\" | \"full\"", "\"sample\"", <><code>sample</code>: up to <code>citations_per_datum</code> citations inline per data point. <code>full</code>: every citation inline, as long as the whole response has at most 2,000; above that it falls back to a sample, and <code>meta.citations</code> says so (<a href="#per-datum-citations">details</a>).</>],
  ["citations_per_datum", "integer", "5", <>How many citations each data point carries inline (1 to 50).</>],
  ["phase_mode", "\"combined\" | \"split\"", "\"combined\"", <><code>combined</code>: a Phase 2/3 trial counts once, in a &quot;Phase 2/Phase 3&quot; bucket. <code>split</code>: it counts in both phases.</>],
  ["condition_source", "\"mesh\" | \"raw\"", "\"mesh\"", <>Group conditions by their MeSH terms, or by the text the sponsor registered.</>],
  ["include_unknown", "boolean", "true", <>Show a &quot;Not reported&quot; bucket for trials without a value.</>],
  ["edge_metric", "\"count\" | \"jaccard\"", "\"count\"", <>Networks only: edge width is shared trials, or the Jaccard similarity.</>],
  ["hide_query_entity", "boolean", "false", <>Networks only: drop the node for the entity you asked about (it links to everything).</>],
];

const CHART_TYPES: [string, React.ReactNode, React.ReactNode][] = [
  ["bar_chart", <><code>x</code> (nominal or ordinal category), <code>y</code> (quantitative)</>,
    <>One bar per row, in the order of <code>data</code>. <code>x.sort</code> is <code>natural</code> (phases, statuses: keep the order) or <code>descending</code> (ranked by <code>y</code>). A &quot;Not reported&quot; bucket, when present, comes last.</>],
  ["grouped_bar_chart", <><code>x</code>, <code>y</code>, <code>color</code> (the group or series)</>,
    <>Long format: one row per category and group. Pivot on <code>color.field</code> (<code>group</code> for <code>compare</code> groups). Keys look like <code>pembrolizumab|PHASE2</code>.</>],
  ["time_series", <><code>x</code> (temporal, <code>time_unit: &quot;year&quot;</code>), <code>y</code>, optional <code>color</code></>,
    <>One line per <code>color</code> value (or a single line). Years are strings (<code>&quot;2015&quot;</code>) and zero-filled. <code>estimated_count</code> per row is how many of its trials have an anticipated, not actual, date.</>],
  ["histogram", <><code>x</code> (<code>bin_start</code>), <code>y</code> (<code>count</code>)</>,
    <>Each row is a bin from <code>bin_start</code> to <code>bin_end</code>. The last bin may have <code>is_overflow: true</code> and <code>bin_end: null</code>: everything above the 99th percentile. <code>meta.notes</code> states the bin width.</>],
  ["scatter_plot", <><code>x</code>, <code>y</code> (quantitative), <code>id</code> (<code>nct_id</code>)</>,
    <>One point per trial that reports both values. <code>estimated: true</code> marks a point built from an estimated value.</>],
  ["network_graph", <><code>node_id</code>, <code>node_label</code>, <code>node_size</code>, <code>node_color</code>, <code>edge_source</code>, <code>edge_target</code>, <code>edge_width</code></>,
    <><code>data</code> is <code>{"{"} nodes, edges {"}"}</code> instead of a list. Node colour is <code>community</code> (one entity type) or <code>type</code> (two). Nodes also carry <code>degree</code> and <code>is_query_entity</code>; edges carry both <code>weight</code> and <code>jaccard</code>.</>],
  ["metric", <><code>value</code> (quantitative, with <code>unit</code>)</>,
    <>A single number: <code>data</code> has one row, <code>{"{"} key: &quot;all&quot;, value, label {"}"}</code>.</>],
];

const META_FIELDS: [string[], React.ReactNode][] = [
  [["interpretation"], <>How the question was read: <code>intent</code>, <code>chart_type</code>, <code>dimension</code>, <code>dimension_2</code>, <code>measure</code>, and <code>chart_type_source</code> (<code>ai</code>, <code>user</code> when you set <code>chart_type</code>, or <code>fallback</code> when the chart type was swapped for one that fits).</>],
  [["filters"], <>The filters actually applied, after merging your fields with the question, under normalised names (<code>drugs</code>, <code>conditions</code>, <code>statuses</code>, <code>start_year_min</code>, <code>groups</code>...).</>],
  [["assumptions"], <>Readings the AI had to choose, in plain sentences. Show them to users.</>],
  [["warnings"], <>Things to know, such as a field overriding the question, or a chart type that didn&apos;t fit.</>],
  [["counting_rule"], <>One sentence on what each value counts, e.g. &quot;Each trial is counted once per country where it has at least one site.&quot;</>],
  [["unique_trials", "additive"], <><code>unique_trials</code> is the number of distinct trials behind the chart. <code>additive: false</code> means one trial can sit in several buckets, so the values don&apos;t add up to it.</>],
  [["excluded"], <>Trials left out and why, e.g. <code>{"{"} &quot;reason&quot;: &quot;start after 2026&quot;, &quot;count&quot;: 7 {"}"}</code>.</>],
  [["notes"], <>Context for the reader, e.g. &quot;Showing the top 10 of 69 countries.&quot;</>],
  [["api_queries"], <>Every ClinicalTrials.gov API v2 query that was run, with its <code>total_count</code> (and <code>group</code> for comparisons). Open the URL to check the numbers yourself.</>],
  [["sort", "citations"], <>How <code>data</code> is ordered (<code>by</code> x or y, <code>order</code>), and which citation mode was <code>requested</code> and <code>applied</code>, with the <code>reason</code> when they differ (<a href="#per-datum-citations">full citations</a>).</>],
  [["group_overlap", "network"], <>Comparisons: trials shared by each pair of groups. Networks: node and edge counts before and after pruning, and the community algorithm.</>],
  [["data_timestamp", "retrieved_at", "cache"], <>The ClinicalTrials.gov data version, when it was read, and whether the plan and result came from cache (<code>hit</code>, <code>miss</code>, <code>revalidated</code>).</>],
  [["details"], <>Status-specific details for non-chart answers (see <a href="#statuses-errors">statuses</a>).</>],
  [["trace_id", "guard", "planner", "narration", "usage", "timings_ms"], <><code>trace_id</code> identifies the request in our logs. <code>guard</code>, <code>planner</code>, <code>narration</code>, <code>usage</code> and <code>timings_ms</code> describe the AI stages, cost and timings. <code>guard.cached: true</code> means a repeat was answered from cache while the daily AI budget was spent, without calling the guard again (see <a href="#limits">limits</a>).</>],
];

const STATUSES: [string, React.ReactNode][] = [
  ["ok", <>A chart: <code>visualization</code> is set.</>],
  ["no_matching_trials", <>The filters are valid but match no trials. <code>meta.details.search_counts</code> lists each search with its count.</>],
  ["out_of_scope", <>The question isn&apos;t about trial registrations (e.g. &quot;does this drug work?&quot;). <code>meta.details.reason</code> says why, and <code>meta.details.suggestion</code> may offer a question that works.</>],
  ["could_not_interpret", <>No valid plan could be made, including when a forced <code>chart_type</code> can&apos;t show the question. <code>meta.details.errors</code> and <code>meta.details.best_attempt</code> explain.</>],
];

const ERRORS: [number, string, React.ReactNode][] = [
  [422, "invalid_request", <>The body failed validation: wrong type, out of range, or an unknown field. <code>details</code> lists each problem as <code>{"{"} loc, msg {"}"}</code>.</>],
  [400, "rejected_by_policy", <>The input safety check rejected the request.</>],
  [401, "unauthorized", <><code>GET /v1/usage</code> without the admin token.</>],
  [404, "not_found", <>Unknown <code>job_id</code>, <code>result_id</code> or data point <code>key</code>, or a path that doesn&apos;t exist.</>],
  [405, "method_not_allowed", <>The path exists but not with this method, e.g. <code>GET /v1/query</code>. The <code>Allow</code> header lists the right one.</>],
  [410, "expired", <>The result, or the finished job, is past its retention (24 hours). Run the query again.</>],
  [429, "too_many_requests", <>Too many requests from your IP (with a <code>Retry-After</code> header in seconds), or too many background jobs at once.</>],
  [503, "upstream_unavailable", <>ClinicalTrials.gov kept failing after retries, or its data changed mid-read. Retry later.</>],
  [503, "llm_unavailable", <>The AI model kept failing, fallback model included.</>],
  [503, "safety_check_unavailable", <>The input safety check failed; requests are refused rather than let through.</>],
  [503, "budget_exceeded", <>Today&apos;s AI budget is spent and the question needs an AI call. Repeats of answered questions still work (see <a href="#limits">limits</a>).</>],
  [500, "internal_error", <>A bug on our side. Quote the <code>trace_id</code> when you report it.</>],
];

function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="docs-table">
      <table>
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} data-label={head[j]}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Endpoint({ method, path }: { method: "GET" | "POST" | "DELETE"; path: string }) {
  return <p className="endpoint"><span className={`method method-${method.toLowerCase()}`}>{method}</span><code>{path}</code></p>;
}

function Toc() {
  return <ol>{SECTIONS.map((s) => <li key={s.id}><a href={`#${s.id}`}>{s.title}</a></li>)}</ol>;
}

export default function DocsPage() {
  const api = publicApiUrl(process.env.PUBLIC_API_URL);
  return (
    <div className="app">
      <DocsTopbar />
      <div className="docs">
        <aside className="docs-toc" aria-label="On this page">
          <p className="docs-toc-title">On this page</p>
          <Toc />
        </aside>
        <main className="docs-body">
          <header className="docs-head">
            <p className="eyebrow">Developer guide</p>
            <h1>API documentation</h1>
            <p className="lede">Send a question about ClinicalTrials.gov, get back a chart spec your code can draw, where every number links to the trials behind it.</p>
            <p className="docs-links">
              <a className="secondary" href={`${api}/docs`}>Try it in Swagger</a>
              <a className="secondary" href={`${api}/redoc`}>Reference (ReDoc)</a>
            </p>
          </header>

          <details className="docs-toc-mobile">
            <summary>On this page</summary>
            <Toc />
          </details>

          <section id="overview" aria-labelledby="overview-h">
            <h2 id="overview-h">Overview</h2>
            <p>The API reads a plain-English question, such as &quot;Which countries have the most recruiting trials for lung cancer?&quot;, plans the matching ClinicalTrials.gov searches, runs them live, and counts the results. It returns a <strong>visualization spec</strong>: the chart type, a title, which data field goes on which axis, and the data itself.</p>
            <p>Every data point carries <strong>citations</strong>: the trials it counts, with the exact record field and value that put each trial there. Nothing in the chart is a number you have to take on trust.</p>
            <dl className="docs-facts">
              <dt>Base URL</dt><dd><code>{api}</code></dd>
              <dt>Format</dt><dd>JSON in, JSON out. No authentication.</dd>
              <dt>Version</dt><dd>Paths start with <code>/v1</code>; responses carry <code>schema_version</code> (now <code>&quot;2.0&quot;</code>).</dd>
            </dl>
            <p>The production API accepts browser calls only from this web app (CORS). Call it from a server, a script or a notebook.</p>
          </section>

          <section id="quick-start" aria-labelledby="quick-start-h">
            <h2 id="quick-start-h">Quick start</h2>
            <p>Ask a question. Most answers take 5 to 40 seconds.</p>
            <CodeBlock label="Request" code={curl(api, "/v1/query", { body: QUICK_BODY })} />
            <p>A real response, trimmed to one of its nine bars, one citation, and part of <code>meta</code>:</p>
            <CodeBlock label="Response 200" code={QUICK_RESPONSE} />
            <p>To draw it: put <code>data[i].phase</code> (from <code>encoding.x.field</code>) on the x axis and <code>data[i].trial_count</code> (from <code>encoding.y.field</code>) on the y axis. To list every trial in the Phase 1 bar, page through <a href="#citations">its citations</a> with <code>result_id</code> and the bar&apos;s <code>key</code>.</p>
          </section>

          <section id="request" aria-labelledby="request-h">
            <h2 id="request-h">The request</h2>
            <Endpoint method="POST" path="/v1/query" />
            <p>Only <code>query</code> is required. The other fields pin down what the question leaves open. <strong>Structured fields override the AI&apos;s reading of the question:</strong> the planner treats them as fixed facts, and if the question disagrees (it says lung cancer, <code>condition</code> says breast cancer) the field wins and <code>meta.warnings</code> records the conflict. Unknown fields are rejected with a 422.</p>
            <Table head={["Field", "Type", "Default", "Meaning"]}
              rows={REQUEST_FIELDS.map(([name, type, def, meaning]) => [<code key="n">{name}</code>, <span key="t" className="type">{type}</span>, <code key="d">{def}</code>, meaning])} />
            <p>For example, a comparison of two drugs, limited to recruiting trials that started in 2018 or later:</p>
            <CodeBlock label="Request with structured fields" code={curl(api, "/v1/query", { body: STRUCTURED_BODY })} />
          </section>

          <section id="response" aria-labelledby="response-h">
            <h2 id="response-h">The response</h2>
            <h3 id="envelope">The envelope</h3>
            <p>Every 200 response has the same five keys, whatever the chart:</p>
            <Table head={["Key", "Meaning"]} rows={[
              [<code key="k">status</code>, <><code>ok</code>, or one of the <a href="#statuses-errors">non-chart statuses</a>.</>],
              [<code key="k">visualization</code>, <>The chart spec, or <code>null</code> when <code>status</code> isn&apos;t <code>ok</code>.</>],
              [<code key="k">meta</code>, <>How the answer was produced: filters, assumptions, counting rule, the API queries run.</>],
              [<code key="k">result_id</code>, <>Identifies the stored result, for <a href="#citations">citations paging</a>. <code>null</code> when nothing was stored.</>],
              [<code key="k">schema_version</code>, <><code>&quot;2.0&quot;</code>. The major version changes when a field is removed or changes meaning.</>],
            ]} />

            <h3 id="visualization">The visualization spec</h3>
            <p><code>visualization</code> has <code>type</code>, <code>title</code>, <code>encoding</code> and <code>data</code>. <code>encoding</code> maps each visual channel to a data field, in the style of Vega-Lite:</p>
            <CodeBlock label="One encoding channel" code={`{ "field": "trial_count", "type": "quantitative", "label": "Number of trials", "unit": "trials", "sort": null, "time_unit": null }`} />
            <p><code>type</code> is <code>quantitative</code>, <code>nominal</code>, <code>ordinal</code> or <code>temporal</code>; <code>sort</code> is <code>ascending</code>, <code>descending</code>, <code>natural</code> or <code>null</code>; <code>time_unit</code> is <code>&quot;year&quot;</code> on temporal axes.</p>
            <p><strong>Render without guessing:</strong> read every data key from <code>encoding[channel].field</code>, and every axis title from <code>label</code> and <code>unit</code>. Field names change with the question (<code>phase</code>, <code>country</code>, <code>start_year</code>, <code>total_enrollment</code>...), the channel names don&apos;t.</p>
            <CodeBlock label="Drawing a bar chart (TypeScript)" code={RENDER_SAMPLE} />

            <h3 id="chart-types">Chart types</h3>
            <Table head={["type", "Channels", "How to draw it"]}
              rows={CHART_TYPES.map(([t, ch, how]) => [<code key="t">{t}</code>, ch, how])} />
            <p>Networks use flat channel names and a <code>{"{"} nodes, edges {"}"}</code> object. From a real melanoma drug network:</p>
            <CodeBlock label="network_graph (trimmed)" code={NETWORK_SAMPLE} />

            <h3 id="per-datum-citations">Per-datum citations</h3>
            <p>Every data point (every bar, year, bin, point, node and edge) carries:</p>
            <ul>
              <li><code>key</code>: a stable identifier, used to <a href="#citations">page through its citations</a>.</li>
              <li><code>citation_count</code>: how many trials are behind it.</li>
              <li><code>citations</code>: the first <code>citations_per_datum</code> of them, in a fixed order (most recent start date first, then NCT ID), or all of them with <code>citations: &quot;full&quot;</code>.</li>
              <li><code>citations_truncated</code>: <code>true</code> when there are more than shown.</li>
            </ul>
            <p><strong>Full citations.</strong> With <code>&quot;citations&quot;: &quot;full&quot;</code>, every data point carries all its citations, as long as the response holds at most 2,000 in total. Above that you get the usual sample instead, and <code>meta.citations</code> says why. Either way, <code>meta.citations</code> reports what you asked for and what you got:</p>
            <CodeBlock label="meta.citations" code={CITATIONS_META_SAMPLE} />
            <p>Trials-per-year charts counted year by year only read a sample of each year, so they always answer with a sample (<code>reason</code> starts with <code>counted per year</code>). For any data point, <a href="#citations">citations paging</a> lists every trial.</p>
            <p>Each citation has the trial&apos;s <code>nct_id</code>, <code>url</code> and <code>title</code>, and <code>evidence</code>: the record fields that put the trial in this bucket, as <code>{"{"} field, excerpt {"}"}</code>. <code>field</code> is a path in the ClinicalTrials.gov study record (e.g. <code>protocolSection.designModule.phases[0]</code>) and <code>excerpt</code> is its exact value. The server checks every excerpt against the record it read before answering.</p>

            <h3 id="meta">Key meta fields</h3>
            <Table head={["Field", "Meaning"]} rows={META_FIELDS.map(([fields, m]) => [<span key="f" className="names">{fields.map((f) => <code key={f}>{f}</code>)}</span>, m])} />
          </section>

          <section id="statuses-errors" aria-labelledby="statuses-errors-h">
            <h2 id="statuses-errors-h">Statuses and errors</h2>
            <h3 id="statuses">Answers that aren&apos;t charts (200)</h3>
            <p>These are valid answers, not errors: HTTP 200 with <code>visualization: null</code>, and <code>meta</code> explaining why.</p>
            <Table head={["status", "When"]} rows={STATUSES.map(([s, w]) => [<code key="s">{s}</code>, w])} />
            <h3 id="errors">Errors</h3>
            <p>Real errors share one body. It never contains internal details; <code>trace_id</code> links it to our logs.</p>
            <CodeBlock label="Error 422" code={ERROR_SAMPLE} />
            <Table head={["HTTP", "code", "When"]} rows={ERRORS.map(([h, c, w]) => [<span key="h" className="http">{h}</span>, <code key="c">{c}</code>, w])} />
            <p>Retry 429 after <code>Retry-After</code> seconds and 503 after a short wait; the others won&apos;t succeed unchanged. Every error uses this body, including a path that doesn&apos;t exist (404) and a wrong method (405).</p>
          </section>

          <section id="jobs" aria-labelledby="jobs-h">
            <h2 id="jobs-h">Background jobs</h2>
            <p>Broad questions can need hundreds of pages from ClinicalTrials.gov. When the estimate is over 60 seconds, <code>POST /v1/query</code> answers <strong>202 Accepted</strong> instead of making you wait:</p>
            <CodeBlock label="Response 202" code={ACCEPTED_SAMPLE} />
            <p>Poll <code>poll_url</code> every second or two (below, <code>$JOB_ID</code> is the <code>job_id</code> from the 202):</p>
            <Endpoint method="GET" path="/v1/jobs/{job_id}" />
            <CodeBlock label="Polling" code={`${curl(api, "/v1/jobs/$JOB_ID")}\n\n${JOB_SAMPLE}`} />
            <ul>
              <li><code>status</code> goes <code>pending</code> → <code>running</code> → <code>succeeded</code> or <code>failed</code>, or <code>cancelled</code> if you cancel it (below).</li>
              <li><code>progress</code> is <code>{"{}"}</code> until retrieval starts, then counts pages: <code>pages_done</code> of <code>pages_total</code>.</li>
              <li>On <code>succeeded</code>, <code>result</code> is the normal response body, exactly as a 200 would have returned it.</li>
              <li>On <code>failed</code>, <code>error</code> is <code>{"{"} code, message, details, trace_id {"}"}</code>, the same fields as an error body. A job that hits a temporary ClinicalTrials.gov or AI failure is retried, up to 3 attempts, before it fails.</li>
            </ul>
            <p>Asking the same question again while its job is still running returns the same job. A finished job is kept for 24 hours, like its result; after that, polling returns <code>410 expired</code>.</p>
            <p>No longer need the answer? Cancel the job, so it stops using ClinicalTrials.gov&apos;s shared rate limit:</p>
            <Endpoint method="DELETE" path="/v1/jobs/{job_id}" />
            <CodeBlock label="Cancelling" code={`${curl(api, "/v1/jobs/$JOB_ID", { method: "DELETE" })}\n\n${CANCELLED_SAMPLE}`} />
            <ul>
              <li>A <code>pending</code> or <code>running</code> job becomes <code>cancelled</code>, with <code>error.code</code> <code>cancelled</code>. Its worker stops within about a second, before the next ClinicalTrials.gov page; <code>progress</code> shows where it stopped.</li>
              <li>A job that has already finished (<code>succeeded</code>, <code>failed</code> or <code>cancelled</code>) comes back unchanged, so cancelling twice is safe. An unknown <code>job_id</code> is <code>404 not_found</code>.</li>
              <li>Anyone with the <code>job_id</code> can cancel the job, just as anyone with it can poll it. It&apos;s a random UUID that only the asker receives, so don&apos;t share it.</li>
              <li>Asking the same question after a cancel starts a new job.</li>
            </ul>
            <p>A question answered in the request (200) can&apos;t be cancelled. If you close the connection early, the server still finishes and stores the answer, so asking the same question again is quick (<code>meta.cache.result</code> is <code>hit</code>). If the question turns out to be broad, its job starts anyway; wait for the 202 if you may want to cancel it.</p>
          </section>

          <section id="citations" aria-labelledby="citations-h">
            <h2 id="citations-h">Citations paging</h2>
            <p>The response usually carries a sample of each data point&apos;s trials. This endpoint lists all of them, in the same order, whatever the citation mode:</p>
            <Endpoint method="GET" path="/v1/results/{result_id}/citations" />
            <Table head={["Parameter", "Meaning"]} rows={[
              [<code key="p">datum</code>, <>Required. The data point&apos;s <code>key</code>, e.g. <code>PHASE1</code>, <code>pembrolizumab|PHASE2</code> or <code>drug:ipilimumab|drug:nivolumab</code>.</>],
              [<code key="p">page_size</code>, <>1 to 100, default 50.</>],
              [<code key="p">cursor</code>, <>Leave it out for the first page; then pass the previous page&apos;s <code>next_cursor</code>.</>],
            ]} />
            <CodeBlock label="First page" code={curl(api, "/v1/results/d70db059-8f32-49a2-9fdc-231f5e3fd056/citations", { query: { datum: "PHASE1", page_size: 50 } })} />
            <CodeBlock label="Response 200 (one citation shown)" code={CITATIONS_SAMPLE} />
            <p><code>next_cursor</code> is <code>null</code> on the last page. Results are kept for 24 hours; after that this endpoint returns <code>410 expired</code>.</p>
          </section>

          <section id="options" aria-labelledby="options-h">
            <h2 id="options-h">Options</h2>
            <Endpoint method="GET" path="/v1/options" />
            <p>The vocabulary the API understands, for building pickers and checking values: dimensions (what a chart can be broken down by), measures (what it counts), chart types, and the allowed values and labels of <code>trial_phase</code>, <code>status</code> and <code>country</code>.</p>
            <CodeBlock label="Request" code={curl(api, "/v1/options")} />
            <CodeBlock label="Response 200 (shape)" code={OPTIONS_SAMPLE} />
          </section>

          <section id="limits" aria-labelledby="limits-h">
            <h2 id="limits-h">Limits</h2>
            <Table head={["Limit", "Value", "When it's reached"]} rows={[
              ["Requests per client IP", "300 per minute, on every /v1 path", <><code>429 too_many_requests</code> with <code>Retry-After</code>.</>],
              ["Background jobs per client IP", "10 pending or running", <><code>429 too_many_requests</code> on the next broad question.</>],
              ["Daily AI budget", "100 USD of model spend per UTC day, for everyone", <>Questions that need an AI call get <code>503 budget_exceeded</code> until midnight UTC. Asking exactly the same question as before still works if its stored answer is valid (<code>meta.cache</code> shows <code>hit</code> or <code>revalidated</code>, with no AI call). Jobs, citations and options keep working.</>],
              ["ClinicalTrials.gov", "9 requests per 10 seconds, shared by all users", <>Requests wait their turn; broad questions become background jobs.</>],
              ["Answer in the request", "60 seconds (estimated)", <>Longer questions become <a href="#jobs">background jobs</a>.</>],
              ["Result retention", "24 hours", <><code>410 expired</code> from citations paging and job polling.</>],
              ["Full citations", "2,000 per response", <>Over it, <code>citations: &quot;full&quot;</code> falls back to a sample; <code>meta.citations.reason</code> says so.</>],
            ]} />
          </section>

          <section id="reference" aria-labelledby="reference-h">
            <h2 id="reference-h">Interactive reference</h2>
            <p>The API publishes its OpenAPI schema, generated from the code, so every field and type is listed there too.</p>
            <ul className="docs-cards">
              <li><a href={`${api}/docs`}><strong>Swagger UI</strong><span>Send real requests from the browser with &quot;Try it out&quot;.</span><code>{api}/docs</code></a></li>
              <li><a href={`${api}/redoc`}><strong>ReDoc</strong><span>Every schema on one readable page.</span><code>{api}/redoc</code></a></li>
              <li><a href={`${api}/openapi.json`}><strong>OpenAPI JSON</strong><span>For client generators and tests.</span><code>{api}/openapi.json</code></a></li>
            </ul>
          </section>
        </main>
      </div>
      <footer className="footer">
        Data from the <a href="https://clinicaltrials.gov/data-api/api" target="_blank" rel="noreferrer">ClinicalTrials.gov API</a>.
        This tool describes trial registrations. It does not say whether a treatment works.
      </footer>
    </div>
  );
}
