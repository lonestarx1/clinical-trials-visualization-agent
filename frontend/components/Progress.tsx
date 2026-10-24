"use client";

import { useEffect, useState } from "react";
import type { JobStatus } from "@/lib/types";

// Approximate stages: the API answers in one request, so this shows typical timing honestly
// ("usually") rather than claiming to know the exact stage.
const STAGES = [
  { after: 0, text: "Checking the question" },
  { after: 2, text: "Planning the chart" },
  { after: 5, text: "Reading trial records from ClinicalTrials.gov" },
  { after: 20, text: "Still reading: broad questions cover thousands of trials" },
];

export function Progress({ job, onStop }: { job: JobStatus | null; onStop: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 500);
    return () => clearInterval(timer);
  }, []);

  const side = (
    <span className="progress-side">
      <span className="muted">{seconds}s</span>
      <button type="button" className="secondary progress-stop" onClick={onStop} title="Stop this question (Esc)">Stop<kbd>Esc</kbd></button>
    </span>
  );

  if (job) {
    const done = job.progress.pages_done ?? 0;
    const total = job.progress.pages_total ?? 0;
    return (
      <div className="progress" role="status" aria-live="polite">
        <div className="progress-head">
          <strong>Large question: running in the background</strong>
          {side}
        </div>
        <p className="muted">
          {total ? `Read ${(done * 1000).toLocaleString()} of about ${(total * 1000).toLocaleString()} trial records.` : "Waiting for a worker."}
          {" "}You can keep this page open; the answer appears here.
        </p>
        <div className="bar"><span style={{ width: `${total ? Math.max(4, (100 * done) / total) : 4}%` }} /></div>
      </div>
    );
  }
  const stage = [...STAGES].reverse().find((s) => seconds >= s.after) ?? STAGES[0];
  return (
    <div className="progress" role="status" aria-live="polite">
      <div className="progress-head"><strong>{stage.text}</strong>{side}</div>
      <p className="muted">Answers usually take 5–30 seconds. Every number comes from live registry data.</p>
      <div className="bar indeterminate"><span /></div>
    </div>
  );
}
