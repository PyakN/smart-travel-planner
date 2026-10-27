import { describe, expect, it } from "vitest";

import {
  categoryIcon,
  categoryLabel,
  dayColor,
  formatDistance,
  formatDuration,
  formatOpeningHours,
  travelLabel,
} from "./format";
import type { PlannedStop } from "./types";

function stop(overrides: Partial<PlannedStop>): PlannedStop {
  return {
    place_id: 1,
    name: "Castelo de São Jorge",
    category: "landmark",
    lat: 38.7139,
    lon: -9.1335,
    arrive: "10:00",
    leave: "10:45",
    travel_mode: "walk",
    travel_min: 11,
    distance_from_previous_m: 716,
    must_visit: false,
    note: null,
    description: null,
    photo: null,
    opening_hours: null,
    website: null,
    ...overrides,
  };
}

describe("formatDistance", () => {
  it("uses metres below 1 km and one decimal above", () => {
    expect(formatDistance(716.4)).toBe("716 m");
    expect(formatDistance(6784)).toBe("6.8 km");
  });
});

describe("formatDuration", () => {
  it.each([
    [45, "45 min"],
    [60, "1 h"],
    [452, "7 h 32 min"],
  ])("%d min -> %s", (minutes, expected) => {
    expect(formatDuration(minutes)).toBe(expected);
  });
});

describe("travelLabel", () => {
  it("describes walking and transit legs", () => {
    expect(travelLabel(stop({}))).toBe("Walk 11 min · 716 m");
    expect(
      travelLabel(stop({ travel_mode: "transit", travel_min: 37, distance_from_previous_m: 6784 })),
    ).toBe("Tram / metro 37 min · 6.8 km");
  });

  it("is empty for the first stop of a free-start day", () => {
    expect(travelLabel(stop({ travel_mode: null, travel_min: 0 }))).toBeNull();
  });
});

describe("labels and colours", () => {
  it("knows backend categories and falls back to a capitalised slug", () => {
    expect(categoryLabel("viewpoint")).toBe("Viewpoint");
    expect(categoryLabel("beach")).toBe("Beach");
  });

  it("cycles day colours", () => {
    expect(dayColor(1)).toBe(dayColor(8));
    expect(dayColor(1)).not.toBe(dayColor(2));
  });
});

describe("formatOpeningHours", () => {
  it.each([
    ["Tu-Su 10:00-18:00", "Tue–Sun 10:00–18:00"],
    [
      "We-Sa 10:00-18:00; Jan 01,May 01,Dec 24-25 off",
      "Wed–Sat 10:00–18:00 · Jan 01, May 01, Dec 24–25 closed",
    ],
    ["Mo-Su 09:00-11:30, 15:00-16:00", "Mon–Sun 09:00–11:30, 15:00–16:00"],
    ["Mo-Fr 10:00-17:00; PH closed", "Mon–Fri 10:00–17:00 · holidays closed"],
    ["24/7", "Open 24/7"],
    ["10:00-20:00;", "10:00–20:00"],
  ])("%s", (raw, expected) => {
    expect(formatOpeningHours(raw)).toBe(expected);
  });
});

describe("categoryIcon", () => {
  it("has an icon per category and a fallback", () => {
    expect(categoryIcon("viewpoint")).toBe("🌅");
    expect(categoryIcon("beach")).toBe("📍");
  });
});
