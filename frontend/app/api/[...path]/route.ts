// Same-origin proxy to the backend (design Q15): the browser only talks to this app, and the
// API address is a runtime setting (API_BASE_URL), not baked into the build.
import type { NextRequest } from "next/server";
import { proxyAllows } from "@/lib/proxy";

async function forward(request: NextRequest, path: string[]): Promise<Response> {
  const target = path.join("/");
  if (!proxyAllows(request.method, target)) return new Response("Not found", { status: 404 });
  const base = process.env.API_BASE_URL ?? "http://localhost:8000";
  const url = `${base}/${target}${request.nextUrl.search}`;
  const headers = new Headers({ accept: "application/json" });
  for (const name of ["content-type", "authorization"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const client = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (client) headers.set("x-forwarded-for", client);
  const upstream = await fetch(url, {
    method: request.method,
    headers,
    body: request.method === "POST" ? await request.text() : undefined,
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      ...(upstream.headers.get("retry-after") ? { "retry-after": upstream.headers.get("retry-after")! } : {}),
    },
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path);
}

// Cancel a background job (the Stop button); the allow-list admits v1/jobs/{id} only.
export async function DELETE(request: NextRequest, context: Context) {
  return forward(request, (await context.params).path);
}
