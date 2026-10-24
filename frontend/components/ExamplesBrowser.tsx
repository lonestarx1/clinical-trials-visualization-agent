"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExampleCard } from "@/components/ExampleCard";
import { exampleFile, pagerLabel, positionOf, step, type Example, type ExampleSummary } from "@/lib/examples";
import { useTheme } from "@/lib/useTheme";

/** Pages through the saved examples one card at a time; the open one is kept in the URL as ?n=. */
export function ExamplesBrowser() {
  const { theme } = useTheme();
  const [list, setList] = useState<ExampleSummary[] | null>(null);
  const [pos, setPos] = useState(0);
  const [example, setExample] = useState<Example | null>(null);
  const [failed, setFailed] = useState(false);
  const cache = useRef(new Map<number, Promise<Example>>());

  // Each answer is its own file, fetched when first shown and kept for the visit.
  const load = useCallback((n: number) => {
    let p = cache.current.get(n);
    if (!p) {
      p = fetch(exampleFile(n)).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))));
      p.catch(() => cache.current.delete(n));
      cache.current.set(n, p);
    }
    return p;
  }, []);

  useEffect(() => {
    fetch("/examples/index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((rows: ExampleSummary[]) => {
        if (!rows.length) throw new Error("empty");
        setPos(positionOf(rows, new URLSearchParams(window.location.search).get("n")));
        setList(rows);
      })
      .catch(() => setFailed(true));
  }, []);

  const n = list?.[pos]?.n;
  useEffect(() => {
    if (n == null || !list) return;
    window.history.replaceState(null, "", `?n=${n}`);
    let current = true;
    setExample(null);
    setFailed(false);
    load(n).then((e) => current && setExample(e)).catch(() => current && setFailed(true));
    if (pos + 1 < list.length) load(list[pos + 1].n).catch(() => {});
    return () => { current = false; };
  }, [n, pos, list, load]);

  const go = useCallback((delta: -1 | 1) => setPos((p) => (list ? step(p, delta, list.length) : p)), [list]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if ((e.target as HTMLElement).closest("input, textarea, select, [role=menu], [role=listbox]")) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  if (!list) {
    return failed
      ? <div className="notice notice-error" role="alert"><h2>The examples couldn&apos;t be loaded</h2><p>Reload the page to try again.</p></div>
      : <div className="skeleton" aria-hidden><span /><span /><span /></div>;
  }

  return (
    <>
      {example && example.n === n
        ? <ExampleCard example={example} theme={theme} />
        : failed
          ? <div className="notice notice-error" role="alert"><h2>This example couldn&apos;t be loaded</h2><p>Go to another one, or reload the page.</p></div>
          : (
            <div className="example-card">
              <header className="example-head">
                <p className="eyebrow">Question {n}</p>
                <h1>{list[pos].question}</h1>
              </header>
              <div className="skeleton" aria-hidden><span /><span /><span /></div>
            </div>
          )}
      <nav className="pager" aria-label="Examples">
        <button className="secondary icon" onClick={() => go(-1)} disabled={pos === 0} aria-label="Previous example">‹</button>
        <span className="pager-count" aria-live="polite">{pagerLabel(list, pos)}</span>
        <button className="secondary icon" onClick={() => go(1)} disabled={pos === list.length - 1} aria-label="Next example">›</button>
      </nav>
    </>
  );
}
