import { describe, expect, it, vi } from "vitest";

import { ApiError, createPlan, errorMessage, getPlan, searchPlaces } from "./api";

function fakeFetch(status: number, body: unknown) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }));
}

describe("createPlan", () => {
  it("posts JSON to the proxied backend", async () => {
    const fetchImpl = fakeFetch(201, { id: 7 });
    const plan = await createPlan({ text: "A day in Lisbon" }, fetchImpl);
    expect(plan.id).toBe(7);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/plan");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ text: "A day in Lisbon" });
  });

  it("surfaces the backend's message", async () => {
    const fetchImpl = fakeFetch(422, { detail: "'tokyo' is not supported yet." });
    await expect(createPlan({ text: "Tokyo" }, fetchImpl)).rejects.toEqual(
      new ApiError(422, "'tokyo' is not supported yet."),
    );
  });

  it("reports an unreachable backend", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    await expect(createPlan({ text: "x" }, fetchImpl)).rejects.toMatchObject({ status: 0 });
  });
});

describe("getPlan", () => {
  it("fetches a saved plan by id", async () => {
    const fetchImpl = fakeFetch(200, { id: 3 });
    await getPlan(3, fetchImpl);
    const [url] = fetchImpl.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/plans/3");
  });
});

describe("searchPlaces", () => {
  it("encodes the query", async () => {
    const fetchImpl = fakeFetch(200, { items: [], total: 0 });
    await searchPlaces("São Jorge & co", { limit: 5 }, fetchImpl);
    const [url] = fetchImpl.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/places?q=S%C3%A3o+Jorge+%26+co&city=lisbon&limit=5");
  });
});

describe("errorMessage", () => {
  it("reads FastAPI validation errors", () => {
    const body = { detail: [{ msg: "String should have at least 1 character", loc: ["body"] }] };
    expect(errorMessage(422, body)).toBe(
      "Invalid request: String should have at least 1 character",
    );
  });

  it("falls back to a message per status", () => {
    expect(errorMessage(503, null)).toMatch(/temporarily unavailable/);
    expect(errorMessage(500, "<html>")).toBe("Something went wrong (HTTP 500).");
  });
});
