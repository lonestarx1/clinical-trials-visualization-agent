import type { ApiError, QueryResponse } from "@/lib/types";

const COPY: Record<string, { title: string; body: string }> = {
  no_matching_trials: { title: "No trials match", body: "Check the spelling of drug and condition names, or remove a filter." },
  out_of_scope: { title: "This isn't something the registry can answer", body: "Try a question about how many trials there are, where they run, who sponsors them, or how they change over time." },
  could_not_interpret: { title: "The question couldn't be turned into a chart", body: "Try naming what to count and how to group it, e.g. “breast cancer trials by phase”." },
  rejected_by_policy: { title: "This request can't be processed", body: "Ask a question about clinical trials." },
  too_many_requests: { title: "Too many questions at once", body: "Wait a moment, then ask again." },
  budget_exceeded: { title: "Today's AI budget is used up", body: "Saved answers still work. New questions will work again tomorrow." },
  upstream_unavailable: { title: "ClinicalTrials.gov isn't responding", body: "This is usually temporary. Ask again in a minute." },
  llm_unavailable: { title: "The AI service isn't responding", body: "Ask again in a minute." },
  safety_check_unavailable: { title: "The safety check isn't available", body: "Questions are only answered after the check. Ask again in a minute." },
  invalid_request: { title: "Some filters aren't valid", body: "Check the years and filter values." },
  stopped: { title: "Stopped", body: "Edit the question or ask again." },
  cancelled: { title: "Stopped", body: "This question was stopped before it finished. Edit the question or ask again." },
};

// Stopping is the user's choice, not a failure: shown plainly, without error styling.
const CHOSEN = new Set(["stopped", "cancelled"]);

export function Notice({ response, error, code: given, onRetry, onAsk }: {
  response?: QueryResponse | null; error?: ApiError["error"] | null; code?: string; onRetry: () => void; onAsk?: (q: string) => void;
}) {
  const code = given ?? error?.code ?? response?.status ?? "";
  const copy = COPY[code] ?? { title: error?.message ?? "Something went wrong", body: "Ask again, or try one of the examples." };
  const details = response?.meta?.details;
  const failed = !!error && !CHOSEN.has(code);
  return (
    <div className={`notice ${failed ? "notice-error" : ""}`} role={failed ? "alert" : "status"}>
      <h2>{copy.title}</h2>
      <p>{details?.reason ? `${details.reason[0].toUpperCase()}${details.reason.slice(1)}. ` : ""}{copy.body}</p>
      {details?.search_counts && (
        <p className="muted small">Searches run: {details.search_counts.map((s: any) => `${s.group ?? "all"}: ${s.count}`).join(", ")}</p>
      )}
      <div className="notice-actions">
        {details?.suggestion && onAsk
          ? <button className="primary" onClick={() => onAsk(details.suggestion)}>Ask instead: {details.suggestion}</button>
          : <button className="secondary" onClick={onRetry}>Ask again</button>}
        {failed && error?.trace_id && <span className="muted small">Reference: <code>{error.trace_id}</code></span>}
      </div>
    </div>
  );
}
