import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Adds the shared secret to the requests the /api proxy forwards to the backend
 * (next.config.ts), so that the API, reachable at its own address too, can refuse requests
 * that did not come through the website (backend/app/origin.py). ORIGIN_SECRET is a
 * server-only setting: it never reaches the browser, and a value the browser sends is
 * replaced. Without it, requests go on unchanged.
 */
export function proxy(request: NextRequest) {
  const secret = process.env.ORIGIN_SECRET;
  if (!secret) return NextResponse.next();
  const headers = new Headers(request.headers);
  headers.set("x-origin-secret", secret);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/api/:path*",
};
