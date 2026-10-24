import type { ApiError, Citation, JobAccepted, JobStatus, QueryResponse } from "./types";

export type QueryOutcome =
  | { kind: "result"; response: QueryResponse }
  | { kind: "job"; job: JobAccepted }
  | { kind: "error"; status: number; error: ApiError["error"] };

async function readError(res: Response): Promise<ApiError["error"]> {
  try {
    const body = await res.json();
    if (body?.error) return body.error;
    return { code: `http_${res.status}`, message: JSON.stringify(body.detail ?? body), details: null, trace_id: "" };
  } catch {
    return { code: `http_${res.status}`, message: res.statusText || "Request failed", details: null, trace_id: "" };
  }
}

export async function postQuery(body: Record<string, unknown>): Promise<QueryOutcome> {
  const res = await fetch("/api/v1/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 202) return { kind: "job", job: await res.json() };
  if (!res.ok) return { kind: "error", status: res.status, error: await readError(res) };
  return { kind: "result", response: await res.json() };
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<JobStatus> {
  const res = await fetch(`/api/v1/jobs/${jobId}`, { cache: "no-store", signal });
  if (!res.ok) throw new Error((await readError(res)).message);
  return res.json();
}

/** Cancel a background job (the Stop button). Best effort: the server stops it within a second. */
export async function cancelJob(jobId: string): Promise<void> {
  try {
    await fetch(`/api/v1/jobs/${jobId}`, { method: "DELETE", keepalive: true });
  } catch {
    // Offline or the page is closing: the job runs on, and its answer is kept for a later ask.
  }
}

export interface CitationPage {
  label: string;
  citation_count: number;
  citations: Citation[];
  next_cursor: number | null;
}

export async function getCitations(resultId: string, datum: string, cursor: number | null): Promise<CitationPage> {
  const params = new URLSearchParams({ datum, page_size: "50" });
  if (cursor !== null) params.set("cursor", String(cursor));
  const res = await fetch(`/api/v1/results/${resultId}/citations?${params}`);
  if (!res.ok) throw new Error((await readError(res)).message);
  return res.json();
}

export interface Options {
  dimensions: { key: string; label: string; kind: string }[];
  chart_types: { key: string }[];
  filters: { trial_phase: { value: string; label: string }[]; status: { value: string; label: string }[]; country: string[] };
}

export async function getOptions(): Promise<Options | null> {
  try {
    const res = await fetch("/api/v1/options");
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}
