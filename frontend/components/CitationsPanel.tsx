"use client";

import { useEffect, useState } from "react";
import { getCitations } from "@/lib/api";
import type { Citation, Datum } from "@/lib/types";

function label(d: Datum): string {
  for (const key of ["label", "phase", "country", "group"]) if (typeof d[key] === "string") return d[key] as string;
  if (d.source && d.target) return `${String(d.source).split(":")[1]} - ${String(d.target).split(":")[1]}`;
  return d.key;
}

export function CitationsPanel({ datum, resultId }: { datum: Datum | null; resultId: string | null }) {
  const [items, setItems] = useState<Citation[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setItems(datum?.citations ?? []);
    setCursor(null);
    setExpanded(false);
    setError(null);
  }, [datum]);

  if (!datum) {
    return <aside className="panel citations"><p className="muted">Click a bar, point, node or link to see the trials behind it.</p></aside>;
  }

  async function loadMore() {
    if (!resultId || !datum) return;
    setLoading(true);
    setError(null);
    try {
      const page = await getCitations(resultId, datum.key, expanded ? cursor : 0);
      setItems((prev) => (expanded ? [...prev, ...page.citations] : page.citations));
      setCursor(page.next_cursor);
      setExpanded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load citations");
    } finally {
      setLoading(false);
    }
  }

  const more = expanded ? cursor !== null : datum.citations_truncated;
  return (
    <aside className="panel citations">
      <h3>{label(datum)}</h3>
      <p className="muted">
        {datum.citation_count.toLocaleString()} contributing trial{datum.citation_count === 1 ? "" : "s"}
        {" · "}showing {items.length}
      </p>
      <ol className="citation-list">
        {items.map((c) => (
          <li key={`${c.nct_id}-${c.rank ?? ""}`}>
            <a href={c.url} target="_blank" rel="noreferrer">{c.nct_id}</a>
            {c.title && <span className="citation-title">{c.title}</span>}
            <ul className="evidence">
              {c.evidence.map((e, i) => (
                <li key={i}><code>{e.field}</code>: <q>{e.excerpt === null ? "(not reported)" : String(e.excerpt)}</q></li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      {more && resultId && (
        <button className="secondary" onClick={loadMore} disabled={loading}>
          {loading ? "Loading…" : expanded ? "Load more" : `View all ${datum.citation_count.toLocaleString()}`}
        </button>
      )}
      {error && <p className="error-text">{error}</p>}
    </aside>
  );
}
