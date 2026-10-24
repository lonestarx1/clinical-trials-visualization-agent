"use client";

import { useEffect, useRef, useState } from "react";
import { Chart } from "@/components/Chart";
import { CitationsPanel } from "@/components/CitationsPanel";
import { MetaPanel } from "@/components/MetaPanel";
import { EMPTY, type FormState, QueryForm, toRequest } from "@/components/QueryForm";
import { getJob, getOptions, type Options, postQuery } from "@/lib/api";
import type { ApiError, Datum, JobStatus, QueryResponse } from "@/lib/types";

const STATUS_TEXT: Record<string, string> = {
  no_matching_trials: "No trials match these filters.",
  out_of_scope: "This question is outside what this service answers.",
  could_not_interpret: "The agent could not turn this question into a valid chart plan.",
};

export default function Home() {
  const [options, setOptions] = useState<Options | null>(null);
  const [busy, setBusy] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<ApiError["error"] | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [selected, setSelected] = useState<Datum | null>(null);
  const [tab, setTab] = useState<"how" | "json">("how");
  const [initialQuery, setInitialQuery] = useState<string>();
  const run = useRef(0);

  useEffect(() => {
    getOptions().then(setOptions);
    // Shareable links: ?q=<question> runs the question on load.
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      setInitialQuery(q);
      ask({ ...EMPTY, query: q });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function ask(form: FormState) {
    const id = ++run.current;
    setBusy(true); setError(null); setResponse(null); setJob(null); setSelected(null);
    try {
      const outcome = await postQuery(toRequest(form));
      if (id !== run.current) return;
      if (outcome.kind !== "job") window.history.replaceState(null, "", `?q=${encodeURIComponent(form.query)}`);
      if (outcome.kind === "error") setError(outcome.error);
      else if (outcome.kind === "result") setResponse(outcome.response);
      else {
        let status = await getJob(outcome.job.job_id);
        while (id === run.current && (status.status === "pending" || status.status === "running")) {
          setJob(status);
          await new Promise((r) => setTimeout(r, 1500));
          status = await getJob(outcome.job.job_id);
        }
        if (id !== run.current) return;
        setJob(null);
        if (status.result) setResponse(status.result);
        else setError(status.error ?? { code: "job_failed", message: "The background job failed.", details: null, trace_id: "" });
      }
    } catch (e) {
      setError({ code: "network_error", message: e instanceof Error ? e.message : "Request failed", details: null, trace_id: "" });
    } finally {
      if (id === run.current) setBusy(false);
    }
  }

  const viz = response?.visualization ?? null;
  return (
    <main>
      <header>
        <h1>ClinicalTrials.gov <span>Query-to-Visualization</span></h1>
        <p>Ask a question about clinical trials. An agent plans the chart; every number is computed from live
          ClinicalTrials.gov data and every data point cites the trials behind it.</p>
      </header>

      <QueryForm options={options} busy={busy} onSubmit={ask} initialQuery={initialQuery} />

      {busy && !job && <div className="panel status"><span className="spinner" /> Planning and fetching live data…</div>}
      {job && (
        <div className="panel status">
          <span className="spinner" /> Broad question: running as a background job.
          {job.progress.pages_total ? ` Fetched ${job.progress.pages_done ?? 0} of ${job.progress.pages_total} pages of trials.` : ""}
          <progress value={job.progress.pages_done ?? 0} max={job.progress.pages_total || 1} />
        </div>
      )}
      {error && (
        <div className="panel error">
          <strong>{error.message}</strong>
          <span className="muted"> ({error.code}{error.trace_id ? `, trace ${error.trace_id}` : ""})</span>
        </div>
      )}

      {response && !viz && (
        <div className="panel">
          <h2>{STATUS_TEXT[response.status] ?? response.status}</h2>
          {response.meta.details?.reason && <p>{response.meta.details.reason}</p>}
          {response.meta.details?.search_counts && <p className="muted">Searches: {JSON.stringify(response.meta.details.search_counts)}</p>}
        </div>
      )}

      {response && viz && (
        <section className="result">
          <div className="panel chart-panel">
            <h2>{viz.title}</h2>
            <p className="summary">{viz.summary}</p>
            <Chart viz={viz} onSelect={setSelected} />
            {response.meta.warnings?.length > 0 && <p className="warning">{response.meta.warnings.join(" ")}</p>}
          </div>
          <CitationsPanel datum={selected} resultId={response.result_id} />
        </section>
      )}

      {response && (
        <section className="panel">
          <div className="tabs">
            <button className={tab === "how" ? "active" : ""} onClick={() => setTab("how")}>How we got this</button>
            <button className={tab === "json" ? "active" : ""} onClick={() => setTab("json")}>Raw JSON</button>
          </div>
          {tab === "how" ? <MetaPanel response={response} /> : <pre className="json">{JSON.stringify(response, null, 2)}</pre>}
        </section>
      )}

      <footer>Data: <a href="https://clinicaltrials.gov/data-api/api" target="_blank" rel="noreferrer">ClinicalTrials.gov API</a>.
        This tool describes trial registrations; it does not assess whether treatments work.</footer>
    </main>
  );
}
