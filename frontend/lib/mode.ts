// Fast mode (design Q22): answer from our daily-synced copy of ClinicalTrials.gov, checked
// against a live count. Live stays the default; the server falls back to live when it must.

export type Mode = "live" | "fast";
export type FastStatus = "ready" | "syncing" | "not_loaded" | "off" | "unknown";

/** The answer's shareable address: the question, the mode when it's fast, a selected data point. */
export function answerUrl(query: string, mode: Mode, datum?: string | null): string {
  return `?q=${encodeURIComponent(query)}${mode === "fast" ? "&mode=fast" : ""}${datum ? `&d=${encodeURIComponent(datum)}` : ""}`;
}

export function modeFrom(search: string): Mode {
  return new URLSearchParams(search).get("mode") === "fast" ? "fast" : "live";
}

const day = (timestamp: string) =>
  new Date(timestamp + "Z").toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** Where the answer's trials came from (`meta.data_source`). */
export function sourceLabel(meta: { data_source?: Mode; data_timestamp?: string | null }): string {
  if (meta.data_source === "fast") {
    return `Fast: our copy of the ${meta.data_timestamp ? `${day(meta.data_timestamp)} ` : ""}data, checked against ClinicalTrials.gov`;
  }
  return "Live from ClinicalTrials.gov";
}

/** What the picker says when fast mode can't answer right now (null when it can). */
export function fastHint(status: FastStatus): string | null {
  switch (status) {
    case "ready": return null;
    case "syncing": return "Our copy is catching up with today's ClinicalTrials.gov update, so fast questions are answered live for a few minutes.";
    case "not_loaded": return "Our copy of ClinicalTrials.gov is still loading, so fast questions are answered live for now.";
    case "off": return "Fast mode is off on this server, so questions are answered live.";
    default: return "Fast mode can't be checked right now, so questions may be answered live.";
  }
}
