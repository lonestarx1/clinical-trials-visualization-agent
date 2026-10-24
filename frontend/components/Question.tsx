"use client";

import { useEffect, useState } from "react";
import { SearchBar } from "@/components/SearchBar";
import type { Options } from "@/lib/api";
import type { FastStatus } from "@/lib/mode";
import { isEditShortcut } from "@/lib/question";
import { activeFilters, type Ask } from "@/lib/request";

// The asked question, in the user's own words, at the head of the answer. It stays in the same
// place while the answer loads, and turns back into the search box when the user edits it.
export function Question({ asked, draft, onDraft, onSubmit, busy, options, fastStatus }: {
  asked: Ask;
  draft: Ask;
  onDraft: (a: Ask) => void;
  onSubmit: (a: Ask) => void;
  busy: boolean;
  options: Options | null;
  fastStatus?: FastStatus;
}) {
  const [editing, setEditing] = useState(false);
  const edit = () => { onDraft(asked); setEditing(true); };

  useEffect(() => {
    if (editing) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (isEditShortcut({ key: e.key, tag: el.tagName, editable: el.isContentEditable, modifier: e.metaKey || e.ctrlKey || e.altKey })) {
        e.preventDefault();
        edit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (editing) {
    return (
      <div className="question question-editing">
        <SearchBar value={draft} onChange={onDraft} busy={busy} options={options} size="large" autoFocus fastStatus={fastStatus}
          onSubmit={(a) => { setEditing(false); onSubmit(a); }} onCancel={() => setEditing(false)} />
      </div>
    );
  }
  const filters = activeFilters(asked);
  return (
    <div className="question">
      <button className="question-text" onClick={edit} title="Edit the question (press /)">
        <span className="sr-only">Your question: </span>{asked.query}
      </button>
      <div className="question-foot">
        {filters.length > 0 && <ul className="question-filters" aria-label="Filters applied">{filters.map((f) => <li key={f.key}>{f.label}</li>)}</ul>}
        <div className="segmented question-mode" role="radiogroup" aria-label="Answer this question live or fast">
          {(["live", "fast"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={asked.mode === m} className={asked.mode === m ? "on" : ""}
              disabled={busy} title={m === "fast" ? "Ask again from our daily copy of ClinicalTrials.gov" : "Ask again straight from ClinicalTrials.gov"}
              onClick={() => { if (asked.mode !== m) onSubmit({ ...asked, mode: m }); }}>{m === "live" ? "Live" : "Fast"}</button>
          ))}
        </div>
        <button className="ghost small-button" onClick={edit}>Edit question<kbd>/</kbd></button>
      </div>
    </div>
  );
}
