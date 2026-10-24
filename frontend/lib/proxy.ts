// What the same-origin proxy (app/api/[...path]) forwards to the backend: an allow-list.

const PUBLIC = /^(v1\/|health$)/;
const ONE_JOB = /^v1\/jobs\/[^/]+$/;

/** True when the proxy may forward `method` to `path` (no leading slash). */
export function proxyAllows(method: string, path: string): boolean {
  if (method === "GET" || method === "POST") return PUBLIC.test(path);
  if (method === "DELETE") return ONE_JOB.test(path); // cancel a background job, nothing else
  return false;
}
