import { describe, expect, it } from "vitest";
import { fullListUrl } from "@/lib/evidence";
import type { Datum } from "@/lib/types";

const datum = (extra: Partial<Datum>): Datum => ({ key: "2015", citation_count: 10, citations: [], citations_truncated: true, ...extra });

describe("fullListUrl", () => {
  it("links to the search when only a sample of a counted bucket is stored", () => {
    expect(fullListUrl(datum({ search_url: "https://clinicaltrials.gov/api/v2/studies?x=1" })))
      .toBe("https://clinicaltrials.gov/api/v2/studies?x=1");
  });

  it("has no link when every trial is stored, or nothing was cut", () => {
    expect(fullListUrl(datum({}))).toBeNull();
    expect(fullListUrl(datum({ search_url: "https://clinicaltrials.gov/x", citations_truncated: false }))).toBeNull();
  });

  it("only links to ClinicalTrials.gov", () => {
    expect(fullListUrl(datum({ search_url: "https://example.com/studies" }))).toBeNull();
  });
});
