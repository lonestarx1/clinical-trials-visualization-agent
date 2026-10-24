"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Answer } from "@/components/Answer";
import { datumLabel, EvidenceDrawer } from "@/components/EvidenceDrawer";
import { Logo } from "@/components/Logo";
import { Notice } from "@/components/Notice";
import { Progress } from "@/components/Progress";
import { Question } from "@/components/Question";
import { SearchBar } from "@/components/SearchBar";
import { ThemePicker } from "@/components/ThemePicker";
import { getJob, getOptions, type Options, postQuery } from "@/lib/api";
import { readRecent, rememberQuestion } from "@/lib/recent";
import { type Ask, EMPTY_ASK, EXAMPLE_GROUPS, toRequestBody } from "@/lib/request";
import type { ApiError, Datum, JobStatus, NetworkData, QueryResponse } from "@/lib/types";
import { useTheme } from "@/lib/useTheme";

type View =
  | { kind: "home" }
  | { kind: "working"; job: JobStatus | null }
  | { kind: "answer"; response: QueryResponse }
  | { kind: "notice"; response?: QueryResponse; error?: ApiError["error"] };

export default function Home() {
  const [options, setOptions] = useState<Options | null>(null);
  const [ask, setAsk] = useState<Ask>(EMPTY_ASK);
  const [asked, setAsked] = useState<Ask | null>(null);
  const [view, setView] = useState<View>({ kind: "home" });
  const [selected, setSelected] = useState<Datum | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const { theme, selection, choose } = useTheme();
  const run = useRef(0);
  const onHome = useRef(true);
  useEffect(() => { onHome.current = view.kind === "home"; }, [view.kind]);

  const submit = useCallback(async (a: Ask) => {
    const id = ++run.current;
    const start = () => { setAsked(a); setSelected(null); setView({ kind: "working", job: null }); };
    // The search box glides into place as the question header (where the browser supports it).
    if (onHome.current && document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      document.startViewTransition(() => flushSync(start));
    } else start();
    setRecent(rememberQuestion(a.query.trim()));
    const keep = new URLSearchParams(window.location.search);
    const d = keep.get("q") === a.query.trim() ? keep.get("d") : null;
    window.history.replaceState(null, "", `?q=${encodeURIComponent(a.query.trim())}${d ? `&d=${encodeURIComponent(d)}` : ""}`);
    try {
      const outcome = await postQuery(toRequestBody(a));
      if (id !== run.current) return;
      if (outcome.kind === "error") return setView({ kind: "notice", error: outcome.error });
      let response: QueryResponse | null = outcome.kind === "result" ? outcome.response : null;
      if (outcome.kind === "job") {
        let job = await getJob(outcome.job.job_id);
        while (id === run.current && (job.status === "pending" || job.status === "running")) {
          setView({ kind: "working", job });
          await new Promise((r) => setTimeout(r, 1500));
          job = await getJob(outcome.job.job_id);
        }
        if (id !== run.current) return;
        if (!job.result) {
          return setView({ kind: "notice", error: job.error ?? { code: "job_failed", message: "The background job failed.", details: null, trace_id: "" } });
        }
        response = job.result;
      }
      setView(response!.visualization ? { kind: "answer", response: response! } : { kind: "notice", response: response! });
      // Deep link to one data point's trials: ?q=...&d=<datum key>
      const wanted = new URLSearchParams(window.location.search).get("d");
      const data = response!.visualization?.data;
      if (wanted && data) {
        const points = Array.isArray(data) ? data : [...data.nodes, ...data.edges];
        setSelected(points.find((p) => p.key === wanted) ?? null);
      }
    } catch {
      if (id === run.current) setView({ kind: "notice", error: { code: "network", message: "Can't reach the server. Check your connection and ask again.", details: null, trace_id: "" } });
    }
  }, []);

  useEffect(() => {
    getOptions().then(setOptions);
    setRecent(readRecent());
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      const a = { ...EMPTY_ASK, query: q };
      setAsk(a);
      submit(a);
    }
  }, [submit]);

  const labels = useMemo(() => {
    const viz = view.kind === "answer" ? view.response.visualization : null;
    if (!viz || Array.isArray(viz.data)) return new Map<string, string>();
    return new Map((viz.data as NetworkData).nodes.map((node) => [node.key, String(node.label)]));
  }, [view]);

  const select = useCallback((d: Datum | null) => {
    setSelected(d);
    const params = new URLSearchParams(window.location.search);
    if (d) params.set("d", d.key); else params.delete("d");
    window.history.replaceState(null, "", `?${params}`);
  }, []);

  const goHome = () => { run.current++; setView({ kind: "home" }); setAsk(EMPTY_ASK); setSelected(null); window.history.replaceState(null, "", "/"); };
  const busy = view.kind === "working";
  const pick = (q: string) => { const a = { ...EMPTY_ASK, query: q }; setAsk(a); submit(a); };

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={goHome} aria-label="Clinical Trials Explorer, start over">
          <Logo />Clinical Trials Explorer
        </button>
        <div className="topbar-actions">
          {view.kind !== "home" && <button className="ghost new-question" onClick={goHome}>New<span className="wide-only"> question</span></button>}
          <ThemePicker selection={selection} onChoose={choose} />
        </div>
      </header>

      {view.kind === "home" && (
        <main className="home">
          <section className="hero">
            <h1>Ask ClinicalTrials.gov a question.<br />Get a chart you can trace to every trial.</h1>
            <p className="lede">Counts, trends, comparisons and networks from over 600,000 registered studies, computed live.
              Click any bar or node to read the exact record lines behind it.</p>
            <SearchBar value={ask} onChange={setAsk} onSubmit={submit} busy={busy} options={options} size="large" />
          </section>
          <section className="examples" aria-label="Example questions">
            {EXAMPLE_GROUPS.map((g) => (
              <div key={g.title} className="example-group">
                <h2>{g.title}</h2>
                <ul>{g.questions.map((q) => <li key={q}><button className="example" onClick={() => pick(q)}>{q}</button></li>)}</ul>
              </div>
            ))}
            {recent.length > 0 && (
              <div className="example-group">
                <h2>Your recent questions</h2>
                <ul>{recent.map((q) => <li key={q}><button className="example" onClick={() => pick(q)}>{q}</button></li>)}</ul>
              </div>
            )}
          </section>
        </main>
      )}

      {view.kind !== "home" && asked && (
        <main className="page">
          <Question asked={asked} draft={ask} onDraft={setAsk} onSubmit={submit} busy={busy} options={options} />
          {view.kind === "working" && <>
            <Progress key={asked.query} job={view.job} />
            <div className="skeleton" aria-hidden><span /><span /><span /></div>
          </>}
          {view.kind === "notice" && <Notice response={view.response} error={view.error} onRetry={() => submit(asked)} />}
          {view.kind === "answer" && <>
            <Answer response={view.response} theme={theme} onSelect={select}
              onCopyLink={() => navigator.clipboard?.writeText(window.location.href)} />
            <EvidenceDrawer datum={selected} resultId={view.response.result_id}
              title={selected ? datumLabel(selected, labels) : ""} onClose={() => select(null)} />
          </>}
        </main>
      )}

      <footer className="footer">
        Data from the <a href="https://clinicaltrials.gov/data-api/api" target="_blank" rel="noreferrer">ClinicalTrials.gov API</a>.
        This tool describes trial registrations. It does not say whether a treatment works.
      </footer>
    </div>
  );
}
