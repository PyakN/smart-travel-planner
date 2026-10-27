import type { PlacePage, PlanRequest, PlanResponse, ReplaceRequest } from "./types";

/** Same-origin prefix; next.config.ts proxies it to the FastAPI backend. */
export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  404: "This plan does not exist.",
  429: "Planning capacity for today is used up. Try again tomorrow.",
  502: "The AI planner failed. Try again.",
  503: "The AI planner is temporarily unavailable. Try again shortly.",
  504: "Planning took too long. Try a shorter trip.",
};

/** FastAPI errors carry `detail`: a string, or a list of validation errors. */
export function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
    return `Invalid request: ${detail[0].msg}`;
  }
  return FALLBACK_MESSAGES[status] ?? `Something went wrong (HTTP ${status}).`;
}

async function request<T>(path: string, init: RequestInit, fetchImpl: typeof fetch): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the planner. Is the backend running?");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, body));
  return body as T;
}

export function createPlan(body: PlanRequest, fetchImpl: typeof fetch = fetch) {
  return request<PlanResponse>(
    "/plan",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fetchImpl,
  );
}

export function getPlan(id: number, fetchImpl: typeof fetch = fetch) {
  return request<PlanResponse>(`/plans/${id}`, { method: "GET" }, fetchImpl);
}

/** Replaces stops of one day; resolves to a new plan version. */
export function replaceStops(
  planId: number,
  body: ReplaceRequest,
  fetchImpl: typeof fetch = fetch,
) {
  return request<PlanResponse>(
    `/plans/${planId}/replace`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fetchImpl,
  );
}

/** Places whose name contains `query` (accents ignored), for the must-visit picker. */
export function searchPlaces(
  query: string,
  {
    city = "lisbon",
    limit = 8,
    signal,
  }: { city?: string; limit?: number; signal?: AbortSignal } = {},
  fetchImpl: typeof fetch = fetch,
) {
  const params = new URLSearchParams({ q: query, city, limit: String(limit) });
  return request<PlacePage>(`/places?${params}`, { method: "GET", signal }, fetchImpl);
}
