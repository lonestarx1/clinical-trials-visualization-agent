"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getCitations } from "@/lib/api";
import type { Citation, Datum } from "@/lib/types";

export function datumLabel(d: Datum, labels: Map<string, string>): string {
  if (d.source && d.target) return `${labels.get(String(d.source)) ?? d.source} – ${labels.get(String(d.target)) ?? d.target}`;
  const parts = ["label", "group"].map((k) => d[k]).filter((v) => typeof v === "string") as string[];
  const named = Object.entries(d).find(([k, v]) =>
    typeof v === "string" && !["key", "group", "label", "nct_id", "id", "type"].includes(k));
  return [named?.[1], ...parts].filter(Boolean).join(" · ") || d.key;
}

/** The last segment of a field path, readable: "protocolSection.designModule.phases[0]" -> "phases". */
const fieldName = (path: string) => path.split(".").pop()?.replace(/\[\d+\]$/, "") ?? path;

export function EvidenceDrawer({ datum, title, resultId, onClose }: {
  datum: Datum | null; title: string; resultId: string | null; onClose: () => void;
}) {
  const [items, setItems] = useState<Citation[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loadedAll, setLoadedAll] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setItems(datum?.citations ?? []);
    setCursor(null); setLoadedAll(false); setError(null); setFilter("");
    if (datum) panel.current?.focus();
  }, [datum]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? items.filter((c) => `${c.nct_id} ${c.title ?? ""}`.toLowerCase().includes(q)) : items;
  }, [items, filter]);

  if (!datum) return null;
  const total = datum.citation_count;
  const more = loadedAll ? cursor !== null : datum.citations_truncated;

  async function load() {
    if (!resultId || !datum) return;
    setLoading(true); setError(null);
    try {
      const page = await getCitations(resultId, datum.key, loadedAll ? cursor : 0);
      setItems((prev) => (loadedAll ? [...prev, ...page.citations] : page.citations));
      setCursor(page.next_cursor); setLoadedAll(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The trial list could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabIndex={-1} ref={panel}>
        <header className="drawer-head">
          <div>
            <p className="muted small">Trials behind this data point</p>
            <h2 id="drawer-title">{title}</h2>
            <p className="muted">{total.toLocaleString()} trial{total === 1 ? "" : "s"}, most recent start first</p>
          </div>
          <button className="ghost icon" onClick={onClose} aria-label="Close">×</button>
        </header>
        {items.length > 8 && (
          <input className="drawer-filter" placeholder="Filter by NCT ID or title" value={filter}
            onChange={(e) => setFilter(e.target.value)} aria-label="Filter trials" />
        )}
        <ol className="evidence-list">
          {shown.map((c) => (
            <li key={`${c.nct_id}-${c.rank ?? ""}`} className="trial">
              <div className="trial-head">
                <a href={c.url} target="_blank" rel="noreferrer" className="nct">{c.nct_id}</a>
                <span className="trial-title">{c.title}</span>
              </div>
              <ul className="record">
                {c.evidence.map((e, i) => (
                  <li key={i}>
                    <span className="record-field" title={e.field}>{fieldName(e.field)}</span>
                    {e.excerpt === null
                      ? <span className="record-missing">not reported</span>
                      : <mark>{String(e.excerpt)}</mark>}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
        {total === 0 && <p className="muted">No trials fall in this bucket.</p>}
        {more && resultId && (
          <button className="secondary wide" onClick={load} disabled={loading}>
            {loading ? "Loading…" : loadedAll ? "Load more" : `Show all ${total.toLocaleString()} trials`}
          </button>
        )}
        {error && <p className="error-text">{error}</p>}
        <p className="muted small drawer-foot">
          Each highlighted value is copied exactly from the trial&apos;s ClinicalTrials.gov record; hover the field
          name for its full path.
        </p>
      </aside>
    </>
  );
}
