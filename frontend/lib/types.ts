// Types of the backend response (design Q12). Mirrors app/schemas/response.py.

export type ChartType =
  | "bar_chart" | "grouped_bar_chart" | "time_series" | "histogram"
  | "scatter_plot" | "network_graph" | "metric";

export interface Channel {
  field: string;
  type: "quantitative" | "nominal" | "ordinal" | "temporal";
  label: string;
  unit?: string | null;
  sort?: "ascending" | "descending" | "natural" | null;
  time_unit?: "year" | null;
}

export interface Evidence { field: string; excerpt: string | number | boolean | null }
export interface Citation { nct_id: string; url: string; title: string | null; evidence: Evidence[]; rank?: number }

export type Datum = Record<string, unknown> & {
  key: string;
  citation_count: number;
  citations: Citation[];
  citations_truncated: boolean;
};

export interface NetworkData { nodes: Datum[]; edges: Datum[] }

export interface Visualization {
  type: ChartType;
  title: string;
  summary: string;
  encoding: Record<string, Channel>;
  data: Datum[] | NetworkData;
}

export interface QueryResponse {
  schema_version: string;
  result_id: string | null;
  status: "ok" | "no_matching_trials" | "out_of_scope" | "could_not_interpret";
  visualization: Visualization | null;
  meta: Record<string, any>;
}

export interface JobAccepted { job_id: string; status: "pending"; poll_url: string; estimated_seconds: number }

export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  progress: { stage?: string; pages_done?: number; pages_total?: number };
  estimated_seconds: number;
  result: QueryResponse | null;
  error: ApiError["error"] | null;
}

export interface ApiError { error: { code: string; message: string; details: unknown; trace_id: string } }
