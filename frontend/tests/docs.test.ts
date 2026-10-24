import { describe, expect, it } from "vitest";
import { curl, DEFAULT_PUBLIC_API_URL, publicApiUrl } from "@/lib/docs";

describe("publicApiUrl", () => {
  it("defaults to the production API when the setting is missing or blank", () => {
    expect(DEFAULT_PUBLIC_API_URL).toBe("https://api.cheiron.engineeradriel.com");
    expect(publicApiUrl(undefined)).toBe(DEFAULT_PUBLIC_API_URL);
    expect(publicApiUrl("")).toBe(DEFAULT_PUBLIC_API_URL);
    expect(publicApiUrl("   ")).toBe(DEFAULT_PUBLIC_API_URL);
  });

  it("uses the setting, trimmed and without trailing slashes", () => {
    expect(publicApiUrl("http://localhost:8000")).toBe("http://localhost:8000");
    expect(publicApiUrl(" https://api.example.org/ ")).toBe("https://api.example.org");
    expect(publicApiUrl("https://api.example.org//")).toBe("https://api.example.org");
  });

  it("ignores a value that is not an http(s) URL", () => {
    expect(publicApiUrl("api.example.org")).toBe(DEFAULT_PUBLIC_API_URL);
    expect(publicApiUrl("javascript:alert(1)")).toBe(DEFAULT_PUBLIC_API_URL);
  });
});

describe("curl", () => {
  const base = "https://api.example.org";

  it("builds a GET", () => {
    expect(curl(base, "/v1/options")).toBe("curl -s https://api.example.org/v1/options");
  });

  it("quotes a URL with a query string", () => {
    expect(curl(base, "/v1/results/abc/citations", { query: { datum: "PHASE2", page_size: 50 } })).toBe(
      "curl -s 'https://api.example.org/v1/results/abc/citations?datum=PHASE2&page_size=50'",
    );
  });

  it("encodes query values", () => {
    expect(curl(base, "/x", { query: { datum: "pembrolizumab|PHASE2" } })).toBe(
      "curl -s 'https://api.example.org/x?datum=pembrolizumab%7CPHASE2'",
    );
  });

  it("builds a POST with a pretty JSON body", () => {
    expect(curl(base, "/v1/query", { body: { query: "Trials by phase", top_n: 5 } })).toBe(
      [
        "curl -s https://api.example.org/v1/query \\",
        "  -H 'Content-Type: application/json' \\",
        "  -d '{",
        '  "query": "Trials by phase",',
        '  "top_n": 5',
        "}'",
      ].join("\n"),
    );
  });

  it("builds a DELETE", () => {
    expect(curl(base, "/v1/jobs/$JOB_ID", { method: "DELETE" })).toBe(
      "curl -s -X DELETE https://api.example.org/v1/jobs/$JOB_ID",
    );
  });

  it("escapes single quotes in the body for the shell", () => {
    expect(curl(base, "/v1/query", { body: { query: "Merck's trials" } })).toContain(`"Merck'\\''s trials"`);
  });
});
