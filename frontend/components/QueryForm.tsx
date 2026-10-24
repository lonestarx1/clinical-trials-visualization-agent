"use client";

import { useEffect, useState } from "react";
import type { Options } from "@/lib/api";

export const EXAMPLES = [
  "How has the number of trials for pembrolizumab changed per year since 2015?",
  "How many trials started each year for Alzheimer's disease?",
  "How are breast cancer trials distributed across phases?",
  "What are the most common intervention types for melanoma trials?",
  "Compare phases for trials involving pembrolizumab vs nivolumab.",
  "Compare sponsor categories across breast cancer and lung cancer.",
  "Which countries have the most recruiting trials for lung cancer?",
  "Show a network of sponsors and drugs for multiple myeloma trials.",
  "Which drugs frequently co-occur in combination studies for melanoma?",
  "What is the distribution of enrollment sizes for Phase 3 Alzheimer's disease trials?",
];

export interface FormState {
  query: string;
  drug_name: string;
  condition: string;
  sponsor: string;
  country: string;
  trial_phase: string[];
  status: string[];
  start_year: string;
  end_year: string;
  chart_type: string;
  citations_per_datum: string;
}

export const EMPTY: FormState = {
  query: "", drug_name: "", condition: "", sponsor: "", country: "", trial_phase: [], status: [],
  start_year: "", end_year: "", chart_type: "", citations_per_datum: "5",
};

/** Only the fields the user filled in: the backend treats every field as authoritative. */
export function toRequest(f: FormState): Record<string, unknown> {
  const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  const body: Record<string, unknown> = { query: f.query.trim() };
  for (const key of ["drug_name", "condition", "sponsor", "country"] as const) {
    const values = list(f[key]);
    if (values.length) body[key] = values;
  }
  if (f.trial_phase.length) body.trial_phase = f.trial_phase;
  if (f.status.length) body.status = f.status;
  if (f.start_year) body.start_year = Number(f.start_year);
  if (f.end_year) body.end_year = Number(f.end_year);
  if (f.chart_type) body.chart_type = f.chart_type;
  body.citations_per_datum = Number(f.citations_per_datum || 5);
  return body;
}

export function QueryForm({ options, busy, onSubmit, initialQuery }: {
  options: Options | null; busy: boolean; onSubmit: (f: FormState) => void; initialQuery?: string;
}) {
  const [form, setForm] = useState<FormState>(EMPTY);
  useEffect(() => { if (initialQuery) setForm((f) => ({ ...f, query: initialQuery })); }, [initialQuery]);
  const [advanced, setAdvanced] = useState(false);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  const toggle = (key: "trial_phase" | "status", value: string) =>
    set(key, form[key].includes(value) ? form[key].filter((v) => v !== value) : [...form[key], value]);

  return (
    <form className="panel query" onSubmit={(e) => { e.preventDefault(); if (form.query.trim()) onSubmit(form); }}>
      <label htmlFor="query" className="sr-only">Question</label>
      <textarea
        id="query" rows={2} maxLength={1000} value={form.query} placeholder="Ask about clinical trials, e.g. How are breast cancer trials distributed across phases?"
        onChange={(e) => set("query", e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (form.query.trim()) onSubmit(form); } }}
      />
      <div className="row">
        <button type="submit" disabled={busy || !form.query.trim()}>{busy ? "Working…" : "Ask"}</button>
        <button type="button" className="link" onClick={() => setAdvanced(!advanced)}>
          {advanced ? "Hide fields" : "Structured fields"}
        </button>
      </div>
      {advanced && (
        <div className="fields">
          {(["drug_name", "condition", "sponsor", "country"] as const).map((key) => (
            <label key={key}>{key.replace("_", " ")}
              <input value={form[key]} placeholder="comma-separated" onChange={(e) => set(key, e.target.value)}
                list={key === "country" ? "countries" : undefined} />
            </label>
          ))}
          <datalist id="countries">{options?.filters.country.map((c) => <option key={c} value={c} />)}</datalist>
          <label>Start year from<input type="number" min={1900} max={2036} value={form.start_year} onChange={(e) => set("start_year", e.target.value)} /></label>
          <label>to<input type="number" min={1900} max={2036} value={form.end_year} onChange={(e) => set("end_year", e.target.value)} /></label>
          <label>Chart type
            <select value={form.chart_type} onChange={(e) => set("chart_type", e.target.value)}>
              <option value="">Let the agent choose</option>
              {options?.chart_types.map((c) => <option key={c.key} value={c.key}>{c.key.replaceAll("_", " ")}</option>)}
            </select>
          </label>
          <label>Citations per data point
            <input type="number" min={1} max={50} value={form.citations_per_datum} onChange={(e) => set("citations_per_datum", e.target.value)} />
          </label>
          <fieldset><legend>Phase</legend>
            {options?.filters.trial_phase.map((p) => (
              <label key={p.value} className="chip"><input type="checkbox" checked={form.trial_phase.includes(p.value)} onChange={() => toggle("trial_phase", p.value)} />{p.label}</label>
            ))}
          </fieldset>
          <fieldset><legend>Overall status</legend>
            {options?.filters.status.map((s) => (
              <label key={s.value} className="chip"><input type="checkbox" checked={form.status.includes(s.value)} onChange={() => toggle("status", s.value)} />{s.label}</label>
            ))}
          </fieldset>
        </div>
      )}
      <div className="examples">
        {EXAMPLES.map((q) => (
          <button type="button" key={q} className="example" disabled={busy}
            onClick={() => { const next = { ...form, query: q }; setForm(next); onSubmit(next); }}>{q}</button>
        ))}
      </div>
    </form>
  );
}
