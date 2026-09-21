import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxy(request: NextRequest, context: RouteContext) {
  const backendUrl = process.env.BACKEND_API_URL ?? "http://localhost:8000";
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`${path.join("/")}${incomingUrl.search}`, `${backendUrl}/`);
  const headers = new Headers();

  for (const name of ["accept", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer(),
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    const contentType = response.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);

    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (caught) {
    const detail = caught instanceof Error ? caught.message : "Backend request failed";
    return Response.json({ detail }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const OPTIONS = proxy;
