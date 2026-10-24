"use client";

import { useEffect, useRef, useState } from "react";
import type { Options } from "@/lib/api";
import { activeFilters, type Ask, EMPTY_ASK } from "@/lib/request";

export function SearchBar({ value, onChange, onSubmit, busy, options, size = "large", autoFocus, onCancel }: {
  value: Ask;
  onChange: (a: Ask) => void;
  onSubmit: (a: Ask) => void;
  busy: boolean;
  options: Options | null;
  size?: "large" | "compact";
  autoFocus?: boolean;
  onCancel?: () => void;
}) {
  const [refining, setRefining] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const set = <K extends keyof Ask>(key: K, v: Ask[K]) => onChange({ ...value, [key]: v });
  const toggle = (key: "trial_phase" | "status", v: string) =>
    set(key, value[key].includes(v) ? value[key].filter((x) => x !== v) : [...value[key], v]);
  const filters = activeFilters(value);
  const submit = () => { if (value.query.trim() && !busy) { setRefining(false); onSubmit(value); } };

  useEffect(() => {
    if (!autoFocus || !input.current) return;
    const el = input.current;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, [autoFocus]);

  useEffect(() => {  // grow with the question, up to a few lines
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value.query]);

  return (
    <div className={`search search-${size}`}>
      <form className="search-box" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label htmlFor="question" className="sr-only">Your question</label>
        <textarea
          id="question" ref={input} rows={1} maxLength={1000} value={value.query}
          placeholder="Ask about trials, e.g. Which countries run the most recruiting lung cancer trials?"
          onChange={(e) => set("query", e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
            if (e.key === "Escape" && onCancel) { e.preventDefault(); onCancel(); }
          }}
        />
        <button type="button" className={`ghost refine ${refining ? "on" : ""}`} aria-expanded={refining}
          onClick={() => setRefining(!refining)}>
          Filters{filters.length ? ` (${filters.length})` : ""}
        </button>
        {onCancel && <button type="button" className="ghost" onClick={onCancel}>Cancel</button>}
        <button type="submit" className="primary" disabled={busy || !value.query.trim()}>
          {busy ? "Working" : "Ask"}
        </button>
      </form>

      {filters.length > 0 && !refining && (
        <div className="chips" aria-label="Filters that will be applied">
          {filters.map((f) => (
            <button key={f.key} className="chip" onClick={() => onChange({ ...value, [f.key]: EMPTY_ASK[f.key],
              ...(f.key === "start_year" ? { end_year: "" } : {}) })} aria-label={`Remove ${f.label}`}>
              {f.label}<span aria-hidden>×</span>
            </button>
          ))}
        </div>
      )}

      {refining && (
        <div className="refine-panel">
          <p className="hint">Filters are applied exactly as written and override the question.</p>
          <div className="refine-grid">
            {([["drug_name", "Drug", "e.g. pembrolizumab"], ["condition", "Condition", "e.g. breast cancer"],
               ["sponsor", "Lead sponsor", "e.g. Merck"], ["country", "Country", "e.g. United States"]] as const).map(([key, label, hint]) => (
              <label key={key}>{label}
                <input value={value[key]} placeholder={hint} onChange={(e) => set(key, e.target.value)}
                  list={key === "country" ? "country-list" : undefined} />
              </label>
            ))}
            <datalist id="country-list">{options?.filters.country.map((c) => <option key={c} value={c} />)}</datalist>
            <label>Started from
              <input inputMode="numeric" placeholder="year" value={value.start_year} onChange={(e) => set("start_year", e.target.value.replace(/\D/g, "").slice(0, 4))} />
            </label>
            <label>Started until
              <input inputMode="numeric" placeholder="year" value={value.end_year} onChange={(e) => set("end_year", e.target.value.replace(/\D/g, "").slice(0, 4))} />
            </label>
            <label>Chart
              <select value={value.chart_type} onChange={(e) => set("chart_type", e.target.value)}>
                <option value="">Best fit for the question</option>
                {options?.chart_types.map((c) => <option key={c.key} value={c.key}>{c.key.replace(/_/g, " ")}</option>)}
              </select>
            </label>
          </div>
          <fieldset><legend>Phase</legend>
            {options?.filters.trial_phase.map((p) => (
              <label key={p.value} className={`toggle ${value.trial_phase.includes(p.value) ? "on" : ""}`}>
                <input type="checkbox" checked={value.trial_phase.includes(p.value)} onChange={() => toggle("trial_phase", p.value)} />{p.label}
              </label>
            ))}
          </fieldset>
          <fieldset><legend>Overall status</legend>
            {options?.filters.status.slice(0, 9).map((s) => (
              <label key={s.value} className={`toggle ${value.status.includes(s.value) ? "on" : ""}`}>
                <input type="checkbox" checked={value.status.includes(s.value)} onChange={() => toggle("status", s.value)} />{s.label}
              </label>
            ))}
          </fieldset>
          <div className="refine-actions">
            <button className="ghost" onClick={() => onChange({ ...EMPTY_ASK, query: value.query })}>Clear filters</button>
            <button className="primary" disabled={busy || !value.query.trim()} onClick={submit}>Ask with filters</button>
          </div>
        </div>
      )}
    </div>
  );
}
