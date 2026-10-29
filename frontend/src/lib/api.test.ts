import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createPlan,
  deleteAccount,
  deleteTrip,
  errorMessage,
  getMe,
  getPlan,
  getTrip,
  listTrips,
  logIn,
  logOut,
  markVisited,
  replaceStops,
  saveTrip,
  searchPlaces,
  signUp,
  unmarkVisited,
  updateTrip,
} from "./api";

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

describe("replaceStops", () => {
  it("posts the day and the ticked stops", async () => {
    const fetchImpl = fakeFetch(201, { id: 9, parent_id: 3 });
    const plan = await replaceStops(3, { day: 2, place_ids: [11, 12] }, fetchImpl);
    expect(plan.parent_id).toBe(3);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/plans/3/replace");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ day: 2, place_ids: [11, 12] });
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

describe("accounts", () => {
  it("signs up and logs in with JSON", async () => {
    const user = { id: 1, email: "ana@example.com", display_name: "Ana", created_at: "" };
    const fetchImpl = fakeFetch(201, user);
    await expect(
      signUp({ email: "ana@example.com", password: "secret12", display_name: "Ana" }, fetchImpl),
    ).resolves.toEqual(user);
    await logIn({ email: "ana@example.com", password: "secret12" }, fetchImpl);
    const calls = fetchImpl.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url, init]) => [url, init.method])).toEqual([
      ["/api/auth/signup", "POST"],
      ["/api/auth/login", "POST"],
    ]);
    expect(JSON.parse(calls[1][1].body as string)).toEqual({
      email: "ana@example.com",
      password: "secret12",
    });
  });

  it("reads a logged-out visitor as null", async () => {
    await expect(getMe(fakeFetch(401, { detail: "Log in first." }))).resolves.toBeNull();
    await expect(getMe(fakeFetch(503, null))).rejects.toMatchObject({ status: 503 });
  });

  it("logs out with an empty answer", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    await expect(logOut(fetchImpl)).resolves.toBeUndefined();
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/auth/logout", "POST"]);
  });
});

describe("trips", () => {
  it("saves a plan by its id", async () => {
    const fetchImpl = fakeFetch(201, { id: 4 });
    await saveTrip(12, fetchImpl);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/trips", "POST"]);
    expect(JSON.parse(init.body as string)).toEqual({ plan_id: 12 });
  });

  it("switches a trip to another version", async () => {
    const fetchImpl = fakeFetch(200, { id: 4 });
    await updateTrip(4, { plan_id: 13 }, fetchImpl);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/trips/4", "PATCH"]);
    expect(JSON.parse(init.body as string)).toEqual({ plan_id: 13 });
  });

  it("lists, opens and deletes trips", async () => {
    const fetchImpl = vi.fn(async () => new Response("[]", { status: 200 }));
    await listTrips(fetchImpl);
    await getTrip(4, fetchImpl);
    await deleteTrip(4, fetchImpl);
    await deleteAccount(fetchImpl);
    const calls = fetchImpl.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url, init]) => `${init.method} ${url}`)).toEqual([
      "GET /api/trips",
      "GET /api/trips/4",
      "DELETE /api/trips/4",
      "DELETE /api/auth/me",
    ]);
  });

  it("ticks and unticks visited stops", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}", { status: 200 }));
    await markVisited(4, 77, fetchImpl);
    await unmarkVisited(4, 77, fetchImpl);
    const calls = fetchImpl.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url, init]) => `${init.method} ${url}`)).toEqual([
      "PUT /api/trips/4/visits/77",
      "DELETE /api/trips/4/visits/77",
    ]);
  });

  it("surfaces other users' trips as not found", async () => {
    await expect(getTrip(9, fakeFetch(404, { detail: "trip not found" }))).rejects.toEqual(
      new ApiError(404, "trip not found"),
    );
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
