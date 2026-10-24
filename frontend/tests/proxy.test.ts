import { describe, expect, it } from "vitest";
import { proxyAllows } from "@/lib/proxy";

describe("proxyAllows", () => {
  it("passes reads and questions through to the API", () => {
    expect(proxyAllows("GET", "v1/options")).toBe(true);
    expect(proxyAllows("GET", "v1/jobs/8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11")).toBe(true);
    expect(proxyAllows("GET", "health")).toBe(true);
    expect(proxyAllows("POST", "v1/query")).toBe(true);
  });

  it("allows DELETE only to cancel one job", () => {
    expect(proxyAllows("DELETE", "v1/jobs/8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11")).toBe(true);
    expect(proxyAllows("DELETE", "v1/jobs")).toBe(false);
    expect(proxyAllows("DELETE", "v1/jobs/abc/extra")).toBe(false);
    expect(proxyAllows("DELETE", "v1/results/abc")).toBe(false);
    expect(proxyAllows("DELETE", "health")).toBe(false);
  });

  it("refuses paths outside the public API", () => {
    expect(proxyAllows("GET", "docs")).toBe(false);
    expect(proxyAllows("GET", "openapi.json")).toBe(false);
    expect(proxyAllows("GET", "healthz")).toBe(false);
  });

  it("refuses methods the app never sends", () => {
    expect(proxyAllows("PUT", "v1/query")).toBe(false);
    expect(proxyAllows("PATCH", "v1/jobs/abc")).toBe(false);
  });
});
