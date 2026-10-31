import { describe, expect, it } from "vitest";

import type { PlannedDay, PlannedStop } from "./types";
import {
  cuisineLabel,
  defaultSearchPoint,
  dayUnderWay,
  dietLabels,
  openingLabel,
  stayOptions,
  venueIcon,
  venueTypeLabel,
  walkLabel,
} from "./venues";

describe("venue labels", () => {
  it("names the kind of venue", () => {
    expect(venueTypeLabel("pastry")).toBe("Pastry shop");
    expect(venueTypeLabel("nightclub")).toBe("Club");
    expect(venueIcon("ice_cream")).toBe("ice-cream");
  });

  it("writes OSM cuisines for people", () => {
    expect(cuisineLabel("coffee_shop")).toBe("Coffee shop");
    expect(cuisineLabel("portuguese")).toBe("Portuguese");
  });

  it("says what a venue serves for diets", () => {
    expect(dietLabels({ vegetarian: "only", vegan: "yes", gluten_free: "yes" })).toEqual([
      "Vegetarian only",
      "Vegan options",
      "Gluten-free options",
    ]);
    expect(dietLabels({})).toEqual([]);
  });

  it("gives the distance and the walk", () => {
    expect(walkLabel({ distance_m: 352, walk_min: 7 })).toBe("352 m · 7 min walk");
  });
});

describe("openingLabel", () => {
  it.each([
    ["open", "open", "23:00", "Open until 23:00", "open"],
    ["open", "open", null, "Open", "open"],
    ["open", "closed", "15:00", "Closes at 15:00, before you get there", "closed"],
    ["closed", "open", "19:00", "Opens at 19:00, by the time you get there", "open"],
    ["closed", "closed", "19:00", "Closed · opens at 19:00", "closed"],
    ["closed", "closed", null, "Closed", "closed"],
    ["unknown", "unknown", null, "Opening hours unknown", "unknown"],
  ] as const)("%s now, %s on arrival, changing at %s", (now, arrival, at, text, state) => {
    expect(openingLabel({ open_now: now, open_on_arrival: arrival, changes_at: at })).toEqual({
      text,
      state,
    });
  });
});

function stop(place_id: number, name: string, lat: number): PlannedStop {
  return { place_id, name, lat, lon: -9.14 } as PlannedStop;
}

const DAY = {
  day: 1,
  stops: [stop(1, "Rossio", 38.71), stop(2, "Castelo", 38.713), stop(3, "Alfama", 38.711)],
  date: "2026-11-02",
  start: "09:30",
  end: "21:30",
} as PlannedDay;

describe("defaultSearchPoint", () => {
  const visit = (place_id: number) => ({ place_id, name: "", visited_at: "" });

  it("is the stop visited last, in the order they were ticked", () => {
    const visits = [visit(3), visit(1), visit(99)]; // 99: another day's stop
    expect(defaultSearchPoint(DAY, visits, null)).toEqual({
      lat: 38.71,
      lon: -9.14,
      label: "Rossio, last visited",
    });
  });

  it("is the start point, or else the first stop, before any visit", () => {
    const hotel = { lat: 38.7, lon: -9.13, round_trip: true };
    expect(defaultSearchPoint(DAY, [], hotel)).toEqual({
      lat: 38.7,
      lon: -9.13,
      label: "your start point",
    });
    expect(defaultSearchPoint(DAY, [], null)?.label).toBe("Rossio, the first stop");
  });
});

describe("dayUnderWay", () => {
  it("is true from the day's midnight until its end", () => {
    expect(dayUnderWay(DAY, { date: "2026-11-02", minutes: 7 * 60 })).toBe(true);
    expect(dayUnderWay(DAY, { date: "2026-11-02", minutes: 21 * 60 + 29 })).toBe(true);
    expect(dayUnderWay(DAY, { date: "2026-11-02", minutes: 21 * 60 + 30 })).toBe(false);
    expect(dayUnderWay(DAY, { date: "2026-11-01", minutes: 12 * 60 })).toBe(false);
    expect(dayUnderWay(DAY, { date: "2026-11-03", minutes: 60 })).toBe(false);
  });

  it("runs into the next morning for days that end after midnight", () => {
    const overnight = { ...DAY, start: "16:00", end: "03:00" };
    expect(dayUnderWay(overnight, { date: "2026-11-03", minutes: 2 * 60 + 30 })).toBe(true);
    expect(dayUnderWay(overnight, { date: "2026-11-03", minutes: 3 * 60 })).toBe(false);
  });

  it("is false for plans without dates", () => {
    expect(dayUnderWay({ ...DAY, date: null }, { date: "2026-11-02", minutes: 600 })).toBe(false);
  });
});

describe("stayOptions", () => {
  it("includes the venue's usual stay", () => {
    expect(stayOptions(75).map((o) => o.minutes)).toEqual([15, 30, 45, 60, 75, 90, 120, 150, 180]);
    expect(
      stayOptions(20)
        .map((o) => o.minutes)
        .slice(0, 3),
    ).toEqual([15, 20, 30]);
    expect(stayOptions(90).find((o) => o.minutes === 90)?.label).toBe("1 h 30 min");
  });
});
