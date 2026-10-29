import { describe, expect, it } from "vitest";

import {
  categoryIcon,
  categoryLabel,
  cityDate,
  cityNow,
  clockMinutes,
  clockTime,
  dayColor,
  dayHours,
  dayLength,
  departureLabel,
  describeAdjustment,
  describeDayChange,
  describeDropped,
  describeEdit,
  describeHoursSwap,
  describeWeatherSwap,
  exposedStops,
  formatDate,
  formatDistance,
  formatDuration,
  formatOpeningHours,
  formatTemp,
  freeTimeLabel,
  hasWeather,
  hoursHint,
  rideBadge,
  rideDetails,
  rideName,
  startingNow,
  textColorOn,
  transitCredits,
  travelLabel,
  weatherIcon,
} from "./format";
import type {
  DayForecast,
  PlanEdit,
  PlannedStop,
  PlanResponse,
  StopForecast,
  TransitRide,
} from "./types";

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
    outdoor: true,
    weather: null,
    hours: "daylight",
    wait_min: 0,
    departure: null,
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
  const EDIT: PlanEdit = {
    day: 1,
    kind: "replace",
    replaced: [],
    removed: [],
    added: [],
    next: null,
    adjustments: [],
    dropped: [],
    warnings: [],
  };

  it("names what was replaced and by what", () => {
    const edit: PlanEdit = {
      ...EDIT,
      day: 2,
      replaced: [ref(1, "A"), ref(2, "B")],
      added: [ref(3, "C")],
    };
    expect(describeEdit(edit)).toBe("Day 2: replaced A, B with C.");
    expect(describeEdit({ ...edit, added: [] })).toBe(
      "Day 2: replaced A, B; nothing else fits the day.",
    );
  });

  it("names what a day edit took out and added", () => {
    const edit: PlanEdit = {
      ...EDIT,
      kind: "edit",
      removed: [ref(1, "A")],
      added: [ref(2, "B"), ref(3, "C")],
    };
    expect(describeEdit(edit)).toBe("Day 1: took out A; added B, C.");
    expect(describeEdit({ ...edit, next: ref(3, "C") })).toBe(
      "Day 1: took out A; added B, C (next).",
    );
    expect(describeEdit({ ...edit, added: [], next: ref(4, "D") })).toBe(
      "Day 1: took out A; D next.",
    );
    expect(describeEdit({ ...EDIT, kind: "edit" })).toBe(
      "Day 1: planned the rest of the day again.",
    );
  });

  it("says what a day edit will do", () => {
    expect(describeDayChange(2, 1)).toBe("Take out 2 stops and add 1 place");
    expect(describeDayChange(1, 0)).toBe("Take out 1 stop");
    expect(describeDayChange(0, 3)).toBe("Add 3 places");
    expect(describeDayChange(0, 0)).toBe("Nothing changed yet");
  });

  it("says why a stop is dropped", () => {
    const dropped = { ...ref(1, "Harbour Bar"), reason: "The day would end at 23:10." };
    expect(describeDropped(dropped)).toBe("Harbour Bar: The day would end at 23:10.");
  });

  it("explains adjustments", () => {
    expect(
      describeAdjustment({ removed: ref(1, "A"), added: ref(2, "B"), reason: "For variety." }),
    ).toBe("Also swapped A for B. For variety.");
    expect(
      describeAdjustment({ removed: null, added: ref(2, "B"), reason: "Fills free time." }),
    ).toBe("Also added B. Fills free time.");
  });

  it("names weather swaps", () => {
    const swap = { removed: ref(1, "River Park"), added: ref(2, "City Museum"), reason: "Wet." };
    expect(describeWeatherSwap(swap)).toBe("City Museum instead of River Park");
  });
});

describe("weather", () => {
  const rain: StopForecast = {
    time: "12:00",
    temp_c: 17,
    condition: "rain",
    description: "light rain",
    icon: "10d",
    pop: 62,
    warning: "Light rain likely (62%)",
  };

  it.each([
    ["clear", "01d", "☀️"],
    ["clear", "01n", "🌙"],
    ["clouds", "02d", "🌤️"],
    ["clouds", "03d", "⛅"],
    ["clouds", "04d", "☁️"],
    ["clouds", "02n", "☁️"],
    ["fog", "50d", "🌫️"],
    ["drizzle", "09d", "🌦️"],
    ["rain", "10n", "🌧️"],
    ["snow", "13d", "🌨️"],
    ["thunderstorm", "11d", "⛈️"],
  ] as const)("%s %s is %s", (condition, icon, emoji) => {
    expect(weatherIcon({ condition, icon })).toBe(emoji);
  });

  it("formats temperatures and dates", () => {
    expect(formatTemp(16.6)).toBe("17°");
    expect(formatDate("2026-10-28")).toBe("Wed 28 Oct");
    expect(formatDate("2027-01-01")).toBe("Fri 1 Jan");
  });

  it("counts days from the city's today, not the browser's", () => {
    const newYearsEve = new Date(Date.UTC(2026, 11, 31, 23, 30)); // 23:30 in Lisbon
    expect(cityDate(0, newYearsEve)).toBe("2026-12-31");
    expect(cityDate(1, newYearsEve)).toBe("2027-01-01");
    // Already the 1st in Kyiv, still the 31st in Lisbon.
    expect(cityDate(0, newYearsEve, "Europe/Kyiv")).toBe("2027-01-01");
  });

  it("finds outdoor stops the weather spoils", () => {
    const day: DayForecast = {
      condition: "rain",
      description: "light rain",
      icon: "10d",
      temp_min_c: 16,
      temp_max_c: 17,
      pop: 62,
      sunrise: "07:03",
      sunset: "17:37",
      slots: [],
    };
    const wet = stop({ place_id: 2, weather: rain });
    const dry = stop({ place_id: 3, weather: { ...rain, warning: null } });
    const plan = {
      days: [
        { stops: [wet, dry], weather: day },
        { stops: [stop({})], weather: null },
      ],
    } as unknown as PlanResponse;
    expect(exposedStops(plan)).toEqual([wet]);
    expect(hasWeather(plan)).toBe(true);
    expect(hasWeather({ days: [{ weather: null }] } as unknown as PlanResponse)).toBe(false);
  });
});

describe("day hours", () => {
  it("tells the time in the city, whatever the browser's time zone", () => {
    const moment = new Date(Date.UTC(2026, 9, 27, 16, 7)); // 16:07 UTC
    expect(cityNow("Europe/Lisbon", moment)).toEqual({ date: "2026-10-27", minutes: 16 * 60 + 7 });
    expect(cityNow("Europe/Kyiv", moment)).toEqual({ date: "2026-10-27", minutes: 18 * 60 + 7 });
    const lateNight = new Date(Date.UTC(2026, 9, 27, 23, 30));
    expect(cityNow("Europe/Kyiv", lateNight).date).toBe("2026-10-28");
  });

  it("starts a trip today at the next quarter of an hour", () => {
    expect(startingNow(16 * 60)).toBe("16:00");
    expect(startingNow(16 * 60 + 7)).toBe("16:15");
    expect(startingNow(16 * 60 + 46)).toBe("17:00");
  });

  it("reads clock times, the next morning too", () => {
    expect(clockMinutes("09:30")).toBe(570);
    expect(clockTime(570)).toBe("09:30");
    expect(clockTime(27 * 60)).toBe("03:00");
  });

  it("counts a day that ends after midnight", () => {
    expect(dayLength("09:30", "21:30")).toBe(12 * 60);
    expect(dayLength("16:00", "03:00")).toBe(11 * 60);
    expect(dayLength("10:00", "10:00")).toBe(24 * 60);
  });

  it("explains the hours", () => {
    expect(hoursHint("09:30", "21:30")).toBe("12 h a day.");
    expect(hoursHint("16:00", "03:00")).toBe(
      "11 h a day, until 03:00 the next morning. From 20:00 the plan only has places open at night: bars, fado houses, restaurants and lit squares.",
    );
    expect(hoursHint("10:00", "23:30")).toMatch(/^13 h 30 min a day\. From 20:00/);
    expect(hoursHint("10:00", "10:00")).toBe("Pick an end time after the start.");
    // Today from now, later days from 09:30: today is over at 23:15 if days end at 21:30.
    expect(hoursHint("23:15", "21:30", "09:30")).toBe(
      "Today's hours end at 21:30: start tomorrow, or end the day later.",
    );
    expect(hoursHint("16:15", "21:30", "09:30")).toBe("5 h 15 min today.");
    expect(hoursHint("23:15", "03:00", "09:30")).toMatch(/^3 h 45 min today, until 03:00 the next/);
  });

  it("shows a day's hours and the free time before a place that opens later", () => {
    expect(dayHours({ start: "16:00", end: "03:00" })).toBe("16:00–03:00");
    expect(dayHours({ start: null, end: null })).toBeNull();
    expect(freeTimeLabel({ wait_min: 85, arrive: "20:00" })).toBe(
      "Free time 1 h 25 min: it opens at 20:00",
    );
    expect(freeTimeLabel({ wait_min: 0, arrive: "11:00" })).toBeNull();
    expect(departureLabel({ departure: { lat: 38.7, lon: -9.1, time: "14:05" } })).toBe(
      "From your location at 14:05",
    );
    expect(departureLabel({ departure: null })).toBeNull();
  });

  it("explains picks the hours had no room for", () => {
    const swap = {
      removed: { place_id: 1, name: "Miradouro da Graça" },
      added: { place_id: 2, name: "Museu do Fado" },
      reason: "Your hours leave too little daylight for it.",
    };
    expect(describeHoursSwap(swap)).toBe(
      "Museu do Fado instead of Miradouro da Graça: Your hours leave too little daylight for it.",
    );
  });

  it("labels evening places", () => {
    expect(categoryLabel("nightlife")).toBe("Bar & nightlife");
    expect(categoryIcon("restaurant")).toBe("🍽️");
  });
});
