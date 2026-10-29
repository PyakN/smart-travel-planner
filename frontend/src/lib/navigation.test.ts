import { describe, expect, it } from "vitest";

import { authHref, safeNext } from "./navigation";

describe("safeNext", () => {
  it("keeps paths on this site", () => {
    expect(safeNext("/trips")).toBe("/trips");
    expect(safeNext("/?plan=12&save=1")).toBe("/?plan=12&save=1");
  });

  it("ignores anything that could leave the site", () => {
    for (const next of [null, "", "trips", "//evil.example", "/\\evil.example", "https://x.io"]) {
      expect(safeNext(next)).toBe("/");
    }
  });
});

describe("authHref", () => {
  it("comes back to where the visitor was", () => {
    expect(authHref("/login", "/?plan=12&save=1")).toBe("/login?next=%2F%3Fplan%3D12%26save%3D1");
    expect(authHref("/signup", "/trips")).toBe("/signup?next=%2Ftrips");
  });

  it("leaves the planner out of the link", () => {
    expect(authHref("/login", "/")).toBe("/login");
    expect(authHref("/login", "//evil.example")).toBe("/login");
  });
});
