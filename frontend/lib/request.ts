// What the user asked: the question plus optional structured fields (design Q5).

export interface Ask {
  query: string;
  drug_name: string;
  condition: string;
  sponsor: string;
  country: string;
  trial_phase: string[];
  status: string[];
  start_year: string;
  end_year: string;
  chart_type: string;
}

export const EMPTY_ASK: Ask = {
  query: "", drug_name: "", condition: "", sponsor: "", country: "", trial_phase: [], status: [],
  start_year: "", end_year: "", chart_type: "",
};

export const CITATIONS_INLINE = 5;

/** Only the fields the user filled in: the backend treats every field as authoritative. */
export function toRequestBody(a: Ask): Record<string, unknown> {
  const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  const body: Record<string, unknown> = { query: a.query.trim(), citations_per_datum: CITATIONS_INLINE };
  for (const key of ["drug_name", "condition", "sponsor", "country"] as const) {
    const values = list(a[key]);
    if (values.length) body[key] = values;
  }
  if (a.trial_phase.length) body.trial_phase = a.trial_phase;
  if (a.status.length) body.status = a.status;
  if (a.start_year) body.start_year = Number(a.start_year);
  if (a.end_year) body.end_year = Number(a.end_year);
  if (a.chart_type) body.chart_type = a.chart_type;
  return body;
}

export function activeFilters(a: Ask): { key: keyof Ask; label: string }[] {
  const out: { key: keyof Ask; label: string }[] = [];
  if (a.drug_name) out.push({ key: "drug_name", label: `Drug: ${a.drug_name}` });
  if (a.condition) out.push({ key: "condition", label: `Condition: ${a.condition}` });
  if (a.sponsor) out.push({ key: "sponsor", label: `Sponsor: ${a.sponsor}` });
  if (a.country) out.push({ key: "country", label: `Country: ${a.country}` });
  if (a.trial_phase.length) out.push({ key: "trial_phase", label: `Phase: ${a.trial_phase.length} selected` });
  if (a.status.length) out.push({ key: "status", label: `Status: ${a.status.length} selected` });
  if (a.start_year || a.end_year) out.push({ key: "start_year", label: `Started ${a.start_year || "…"}–${a.end_year || "…"}` });
  if (a.chart_type) out.push({ key: "chart_type", label: `Chart: ${a.chart_type.replace(/_/g, " ")}` });
  return out;
}

export const EXAMPLE_GROUPS: { title: string; questions: string[] }[] = [
  { title: "Change over time", questions: [
    "How has the number of trials for pembrolizumab changed per year since 2015?",
    "How many trials started each year for Alzheimer's disease?",
  ] },
  { title: "Breakdowns", questions: [
    "How are breast cancer trials distributed across phases?",
    "What are the most common intervention types for melanoma trials?",
    "What is the distribution of enrollment sizes for Phase 3 Alzheimer's disease trials?",
  ] },
  { title: "Comparisons", questions: [
    "Compare phases for trials involving pembrolizumab vs nivolumab.",
    "Compare sponsor categories across breast cancer and lung cancer.",
  ] },
  { title: "Where trials run", questions: [
    "Which countries have the most recruiting trials for lung cancer?",
  ] },
  { title: "Connections", questions: [
    "Show a network of sponsors and drugs for multiple myeloma trials.",
    "Which drugs frequently co-occur in combination studies for melanoma?",
  ] },
];
