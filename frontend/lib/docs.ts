// Helpers for the API docs page (app/docs): the public API address and curl snippets.

export const DEFAULT_PUBLIC_API_URL = "https://api.cheiron.engineeradriel.com";

/** The API address shown to developers (PUBLIC_API_URL), trimmed, without trailing slashes. */
export function publicApiUrl(value: string | undefined): string {
  const url = (value ?? "").trim().replace(/\/+$/, "");
  return /^https?:\/\/[^\s/]+/.test(url) ? url : DEFAULT_PUBLIC_API_URL;
}

type CurlOptions = { query?: Record<string, string | number>; body?: unknown; method?: "DELETE" };

const shellQuote = (text: string) => `'${text.replaceAll("'", `'\\''`)}'`;

/** A copy-pasteable curl command: GET by default, POST with a JSON body when `body` is given. */
export function curl(base: string, path: string, { query, body, method }: CurlOptions = {}): string {
  const params = query ? new URLSearchParams(Object.entries(query).map(([k, v]) => [k, String(v)])).toString() : "";
  const url = `${base}${path}${params ? `?${params}` : ""}`;
  const target = /[?&]/.test(url) ? shellQuote(url) : url;
  if (method) return `curl -s -X ${method} ${target}`;
  if (body === undefined) return `curl -s ${target}`;
  return [
    `curl -s ${target} \\`,
    "  -H 'Content-Type: application/json' \\",
    `  -d ${shellQuote(JSON.stringify(body, null, 2))}`,
  ].join("\n");
}
