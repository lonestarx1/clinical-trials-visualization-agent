"use client";

import { Chart } from "@/components/Chart";
import { askUrl, statusWords, type Example } from "@/lib/examples";
import type { Theme } from "@/lib/theme";

const noop = () => {};

/** One saved example: the question, then its chart (or, when there's none, why not). */
export function ExampleCard({ example, theme }: { example: Example; theme: Theme }) {
  const viz = example.status === "ok" ? example.visualization : null;
  return (
    <article className="example-card" aria-labelledby="example-question">
      <header className="example-head">
        <p className="eyebrow">Question {example.n}</p>
        <h1 id="example-question">{example.question}</h1>
      </header>

      {viz ? (
        <div className="figure">
          <h2 className="example-title">{viz.title}</h2>
          {example.unique_trials != null && <p className="muted small">{example.unique_trials.toLocaleString("en-US")} trials</p>}
          <Chart key={example.n} viz={viz} theme={theme} onSelect={noop} />
        </div>
      ) : (
        <div className="notice" role="status">
          <h2>{statusWords(example.status === "ok" ? "could_not_interpret" : example.status)}</h2>
          {example.reason && <p>{example.reason}</p>}
          {example.suggestion && <p className="muted">Try instead: {example.suggestion}</p>}
        </div>
      )}

      <p className="example-ask"><a href={askUrl(example.question)}>Ask this question in the app</a></p>
    </article>
  );
}
