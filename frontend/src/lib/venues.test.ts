import { describe, expect, it } from "vitest";

import type { PlannedDay, PlannedStop } from "./types";
import {
  type SearchPoint,
  cuisineLabel,
  defaultSearchPoint,
  dayUnderWay,
  dietLabels,
  openingLabel,
  placements,
  setOffMoment,
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

function stop(place_id: number, name: string, lat: number, leave = "12:00"): PlannedStop {
  return { place_id, name, lat, lon: -9.14, leave } as PlannedStop;
}

const DAY = {
  day: 1,
  stops: [
    stop(1, "Rossio", 38.71, "10:30"),
    stop(2, "Castelo", 38.713, "12:15"),
    stop(3, "Alfama", 38.711, "14:00"),
  ],
  date: "2026-11-02",
  start: "09:30",
  end: "21:30",
} as PlannedDay;

const visit = (place_id: number) => ({ place_id, name: "", visited_at: "" });

describe("defaultSearchPoint", () => {
  it("is the stop visited last, in the order they were ticked", () => {
    const visits = [visit(3), visit(1), visit(99)]; // 99: another day's stop
    expect(defaultSearchPoint(DAY, visits, null)).toEqual({
      lat: 38.71,
      lon: -9.14,
      label: "Rossio, last visited",
      stop: 1,
      here: true,
    });
  });

  it("is the start point, or else the first stop, before any visit", () => {
    const hotel = { lat: 38.7, lon: -9.13, round_trip: true };
    expect(defaultSearchPoint(DAY, [], hotel)).toEqual({
      lat: 38.7,
      lon: -9.13,
      label: "your start point",
      here: true,
    });
    expect(defaultSearchPoint(DAY, [], null)).toMatchObject({
      label: "Rossio, the first stop",
      stop: 1,
    });
    expect(defaultSearchPoint(DAY, [], null)?.here).toBeUndefined();
  });
});

describe("placements", () => {
  const near = (lat: number, more: Partial<SearchPoint> = {}): SearchPoint => ({
    lat,
    lon: -9.14,
    label: "",
    ...more,
  });

  it("puts a place found around a stop of a day ahead right after it", () => {
    const { options, chosen } = placements(DAY, [], null, near(38.713, { stop: 2 }), false);
    expect(options.map((o) => o.label)).toEqual([
      "First, as the day begins · 09:30",
      "After Rossio · 10:30",
      "After Castelo · 12:15",
      "After Alfama · 14:00",
    ]);
    expect(chosen).toMatchObject({
      key: "2",
      after: { place_id: 2 },
      fromHere: false,
      setOffMin: 12 * 60 + 15,
    });
    expect(chosen.effect).toBe(
      "Day 1 stays as planned up to Castelo, then this place; the rest of the day is planned again from it.",
    );
  });

  it("is next from where the traveller is on a day under way", () => {
    const point = defaultSearchPoint(DAY, [visit(1)], null);
    const { options, chosen } = placements(DAY, [visit(1)], null, point, true);
    expect(options.map((o) => o.label)).toEqual([
      "Next, from where you are now",
      "After Castelo",
      "After Alfama",
    ]);
    expect(chosen).toMatchObject({ key: "here", after: null, fromHere: true, setOffMin: null });
    expect(options[1]).toMatchObject({ after: { place_id: 2 }, fromHere: true });
  });

  it("goes after a stop of a day under way that the traveller is not at", () => {
    // The search from the free evening, around the day's last stop.
    const { chosen } = placements(DAY, [visit(1)], null, near(38.711, { stop: 3 }), true);
    expect(chosen).toMatchObject({ key: "3", fromHere: false, setOffMin: 14 * 60 });
  });

  it("follows the visited stops when the search is around one of them on a day ahead", () => {
    const point = defaultSearchPoint(DAY, [visit(1)], null);
    const { chosen } = placements(DAY, [visit(1)], null, point, false);
    expect(chosen).toMatchObject({
      key: "first",
      label: "Next, after the stops you visited · 10:30",
      setOffMin: 10 * 60 + 30,
    });
  });

  it("goes after the stop nearest a pin, or first when the start point is nearer", () => {
    const pin = { label: "the pin on the map", here: true };
    expect(placements(DAY, [], null, near(38.7112, pin), false).chosen.key).toBe("3");
    const hotel = { lat: 38.7, lon: -9.14, round_trip: true };
    expect(placements(DAY, [], hotel, near(38.701, pin), false).chosen.key).toBe("first");
    expect(placements(DAY, [], null, near(38.701, pin), false).chosen.key).toBe("1");
    const start = defaultSearchPoint(DAY, [], hotel);
    expect(placements(DAY, [], hotel, start, false).chosen.key).toBe("first");
  });

  it("reads times after midnight as the next morning", () => {
    const overnight = {
      ...DAY,
      start: "16:00",
      end: "03:00",
      stops: [stop(1, "Bairro Alto", 38.71, "23:40"), stop(2, "Cais", 38.707, "01:30")],
    };
    const { options } = placements(overnight, [], null, null, false);
    expect(options.map((o) => o.setOffMin)).toEqual([16 * 60, 23 * 60 + 40, 25 * 60 + 30]);
  });
});

describe("setOffMoment", () => {
  const before = { date: "2026-11-01", minutes: 20 * 60 };

  it("is when the traveller sets off on a day ahead, in the city's time", () => {
    expect(setOffMoment(DAY, { setOffMin: 12 * 60 + 15 }, before)).toBe("2026-11-02T12:15");
    expect(setOffMoment(DAY, { setOffMin: 25 * 60 + 30 }, before)).toBe("2026-11-03T01:30");
  });

  it("is now once that time has passed, from where the traveller is, or without dates", () => {
    const noon = { date: "2026-11-02", minutes: 12 * 60 };
    expect(setOffMoment(DAY, { setOffMin: 12 * 60 + 15 }, noon)).toBe("2026-11-02T12:15");
    expect(setOffMoment(DAY, { setOffMin: 11 * 60 }, noon)).toBeNull();
    expect(setOffMoment(DAY, { setOffMin: null }, before)).toBeNull();
    expect(setOffMoment({ date: null }, { setOffMin: 600 }, before)).toBeNull();
  });

  it("goes with what the placement says of that time", () => {
    const ahead = placements(DAY, [], null, null, false).options;
    expect(ahead.map((o) => o.setOff)).toEqual([
      "as the day begins",
      "when you leave Rossio",
      "when you leave Castelo",
      "when you leave Alfama",
    ]);
    const visited = placements(DAY, [visit(1)], null, null, false).chosen;
    expect(visited.setOff).toBe("after the stops you visited");
    const here = defaultSearchPoint(DAY, [visit(1)], null);
    expect(placements(DAY, [visit(1)], null, here, true).chosen.setOff).toBe("now");
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
