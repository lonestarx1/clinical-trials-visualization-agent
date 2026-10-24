import type { Datum } from "@/lib/types";

// Counted buckets (e.g. trials per year from count calls) store only a sample of their trials;
// the full list is the bucket's ClinicalTrials.gov search.
export function fullListUrl(d: Datum): string | null {
  const url = d.search_url;
  if (typeof url !== "string" || !d.citations_truncated) return null;
  return url.startsWith("https://clinicaltrials.gov/") ? url : null;
}
