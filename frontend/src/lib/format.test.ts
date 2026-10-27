import { describe, expect, it } from "vitest";

import {
  categoryIcon,
  categoryLabel,
  dayColor,
  describeAdjustment,
  describeEdit,
  formatDistance,
  formatDuration,
  formatOpeningHours,
  rideBadge,
  rideDetails,
  rideName,
  textColorOn,
  transitCredits,
  travelLabel,
} from "./format";
import type { PlannedStop, PlanResponse, TransitRide } from "./types";

const GREEN_LINE: TransitRide = {
  vehicle: "metro",
  line: "Verde",
  headsign: "Cais Do Sodré",
  color: "#009933",
  board: "Rossio",
  alight: "Cais do Sodré",
  stops: 2,
  minutes: 3,
  attributions: [{ text: "Metropolitano de Lisboa", url: "https://www.metrolisboa.pt" }],
};
const CASCAIS_LINE: TransitRide = {
  ...GREEN_LINE,
  vehicle: "train",
  line: "Linha de Cascais",
  headsign: "Cascais",
  color: "#FFA500",
  stops: 3,
  minutes: 7,
  attributions: [{ text: "CP - Comboios de Portugal", url: null }],
};

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
    rides: [],
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
  const ride = { travel_mode: "transit", travel_min: 24, distance_from_previous_m: 6753 } as const;

  it("describes walks and real rides", () => {
    expect(travelLabel(stop({}))).toBe("Walk 11 min · 716 m");
    expect(travelLabel(stop({ ...ride, rides: [GREEN_LINE, CASCAIS_LINE] }))).toBe(
      "Metro + Train 24 min · 6.8 km",
    );
    expect(travelLabel(stop({ ...ride, rides: [GREEN_LINE, GREEN_LINE] }))).toBe(
      "Metro 24 min · 6.8 km",
    );
  });

  it("marks estimated ride times", () => {
    expect(travelLabel(stop({ ...ride, travel_min: 37 }))).toBe("Tram / metro ~37 min · 6.8 km");
  });

  it("is empty for the first stop of a free-start day", () => {
    expect(travelLabel(stop({ travel_mode: null, travel_min: 0 }))).toBeNull();
  });
});

describe("rides", () => {
  it("names the line, the stops and the direction", () => {
    expect(rideBadge(GREEN_LINE)).toBe("🚇 Verde");
    expect(rideName(GREEN_LINE)).toBe("Metro Verde to Cais Do Sodré");
    expect(rideDetails(GREEN_LINE)).toBe(
      "Rossio → Cais do Sodré · 2 stops · towards Cais Do Sodré",
    );
    const bare = { ...GREEN_LINE, board: null, headsign: null, stops: 1 };
    expect(rideName(bare)).toBe("Metro Verde");
    expect(rideDetails(bare)).toBe("1 stop");
  });

  it("keeps badge text readable on any line colour", () => {
    expect(textColorOn("#009933")).toBe("#ffffff"); // metro green
    expect(textColorOn("#FFA500")).toBe("#18181b"); // train orange
    expect(textColorOn("not a colour")).toBe("#ffffff");
  });

  it("credits each transit operator once", () => {
    const segment = (r: TransitRide | null) => ({
      mode: "transit" as const,
      geometry: [],
      ride: r,
    });
    const plan = {
      days: [
        { segments: [segment(GREEN_LINE), segment(null), segment(CASCAIS_LINE)] },
        { segments: [segment(GREEN_LINE)] },
      ],
    } as unknown as PlanResponse;
    expect(transitCredits(plan).map((c) => c.text)).toEqual([
      "Metropolitano de Lisboa",
      "CP - Comboios de Portugal",
    ]);
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

describe("edit descriptions", () => {
  const ref = (place_id: number, name: string) => ({ place_id, name });

  it("names what was replaced and by what", () => {
    const edit = {
      day: 2,
      replaced: [ref(1, "A"), ref(2, "B")],
      added: [ref(3, "C")],
      adjustments: [],
    };
    expect(describeEdit(edit)).toBe("Day 2: replaced A, B with C.");
    expect(describeEdit({ ...edit, added: [] })).toBe(
      "Day 2: replaced A, B; nothing else fits the day.",
    );
  });

  it("explains adjustments", () => {
    expect(
      describeAdjustment({ removed: ref(1, "A"), added: ref(2, "B"), reason: "For variety." }),
    ).toBe("Also swapped A for B. For variety.");
    expect(
      describeAdjustment({ removed: null, added: ref(2, "B"), reason: "Fills free time." }),
    ).toBe("Also added B. Fills free time.");
  });
});
