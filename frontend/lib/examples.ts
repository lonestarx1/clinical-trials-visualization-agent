// The saved example answers in public/examples (written by scripts/build_examples.py) and the pager over them.
import type { Visualization } from "./types";

export type ExampleStatus = "ok" | "out_of_scope" | "no_matching_trials" | "could_not_interpret" | "rejected";

/** One row of public/examples/index.json. */
export interface ExampleSummary { n: number; question: string; status: ExampleStatus; title: string | null }

/** One public/examples/NNN.json: the API's answer, without its citations. */
export interface Example {
  n: number;
  question: string;
  status: ExampleStatus;
  visualization: Visualization | null;
  unique_trials: number | null;
  reason: string | null;
  suggestion: string | null;
}

export const exampleFile = (n: number) => `/examples/${String(n).padStart(3, "0")}.json`;

/** Where in the list the URL's ?n= points: that example, else the next saved one, else the last; junk opens the first. */
export function positionOf(list: ExampleSummary[], n: string | null): number {
  const wanted = Number(n);
  if (!n || !Number.isInteger(wanted)) return 0;
  const at = list.findIndex((e) => e.n >= wanted);
  return at === -1 ? list.length - 1 : at;
}

/** One step back or forward; the pager stops at the ends rather than wrapping. */
export const step = (pos: number, delta: -1 | 1, length: number) => Math.min(Math.max(pos + delta, 0), length - 1);

/** "12 / 100": the example's own number, out of the highest number saved, so gaps don't renumber the rest. */
export const pagerLabel = (list: ExampleSummary[], pos: number) => `${list[pos].n} / ${list[list.length - 1].n}`;

export const askUrl = (question: string) => `/?q=${encodeURIComponent(question)}&mode=live`;

const WORDS: Record<Exclude<ExampleStatus, "ok">, string> = {
  out_of_scope: "Outside what the trial registry can answer",
  no_matching_trials: "No trials matched",
  could_not_interpret: "The question could not be turned into a chart",
  rejected: "Refused by the safety check",
};

export const statusWords = (status: Exclude<ExampleStatus, "ok">) => WORDS[status];
