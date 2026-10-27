import type {
  Adjustment,
  Attribution,
  ForecastSlot,
  PlanEdit,
  PlannedStop,
  PlanResponse,
  TransitRide,
  TransitVehicle,
  WeatherCondition,
} from "./types";

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

export function formatDuration(minutes: number): string {
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

const CATEGORY_LABELS: Record<string, string> = {
  museum: "Museum",
  gallery: "Gallery",
  landmark: "Landmark",
  monument: "Monument",
  viewpoint: "Viewpoint",
  religious: "Religious site",
  park: "Park",
  culture: "Theatre & arts",
  market: "Market",
  attraction: "Attraction",
};

export function categoryLabel(slug: string): string {
  return CATEGORY_LABELS[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

const VEHICLES: Record<TransitVehicle, { label: string; icon: string }> = {
  metro: { label: "Metro", icon: "🚇" },
  tram: { label: "Tram", icon: "🚋" },
  bus: { label: "Bus", icon: "🚌" },
  train: { label: "Train", icon: "🚆" },
  ferry: { label: "Ferry", icon: "⛴️" },
  funicular: { label: "Funicular", icon: "🚞" },
  cable_car: { label: "Cable car", icon: "🚡" },
  other: { label: "Transit", icon: "🚏" },
};

/**
 * How the traveller reaches this stop: "Walk 11 min · 716 m", "Metro + Train 24 min · 6.8 km",
 * or "Tram / metro ~37 min · 6.8 km" when the ride time is an estimate.
 */
export function travelLabel(stop: PlannedStop): string | null {
  if (!stop.travel_mode) return null;
  const distance = formatDistance(stop.distance_from_previous_m);
  if (stop.travel_mode === "walk") return `Walk ${formatDuration(stop.travel_min)} · ${distance}`;
  if (stop.rides.length === 0)
    return `Tram / metro ~${formatDuration(stop.travel_min)} · ${distance}`;
  const vehicles = [...new Set(stop.rides.map((r) => VEHICLES[r.vehicle].label))].join(" + ");
  return `${vehicles} ${formatDuration(stop.travel_min)} · ${distance}`;
}

/** Badge text for a ride, e.g. "🚋 28E". */
export function rideBadge(ride: TransitRide): string {
  return `${VEHICLES[ride.vehicle].icon} ${ride.line}`;
}

/** "Metro Verde to Cais do Sodré", for map tooltips. */
export function rideName(ride: TransitRide): string {
  const name = `${VEHICLES[ride.vehicle].label} ${ride.line}`;
  return ride.headsign ? `${name} to ${ride.headsign}` : name;
}

/** "Rossio → Cais do Sodré · 2 stops · towards Cais Do Sodré". */
export function rideDetails(ride: TransitRide): string {
  const parts = [`${ride.stops} ${ride.stops === 1 ? "stop" : "stops"}`];
  if (ride.board && ride.alight) parts.unshift(`${ride.board} → ${ride.alight}`);
  if (ride.headsign) parts.push(`towards ${ride.headsign}`);
  return parts.join(" · ");
}

/** Black or white, whichever reads better on a line colour such as "#FFA500". */
export function textColorOn(background: string): string {
  const hex = background.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(hex)) return "#ffffff";
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  // Perceived brightness (ITU-R BT.601 weights).
  return 0.299 * r + 0.587 * g + 0.114 * b > 0.6 ? "#18181b" : "#ffffff";
}

/** The transit operators' data credits for every ride in the plan, once each. */
export function transitCredits(plan: PlanResponse): Attribution[] {
  const credits = new Map<string, Attribution>();
  for (const day of plan.days) {
    for (const segment of day.segments) {
      for (const credit of segment.ride?.attributions ?? []) credits.set(credit.text, credit);
    }
  }
  return [...credits.values()];
}

/** Distinct colours for up to seven days; repeats after that. */
export const DAY_COLORS = [
  "#2563eb",
  "#db2777",
  "#16a34a",
  "#ea580c",
  "#7c3aed",
  "#0891b2",
  "#ca8a04",
];

export function dayColor(day: number): string {
  return DAY_COLORS[(day - 1) % DAY_COLORS.length];
}

const CATEGORY_ICONS: Record<string, string> = {
  museum: "🏛️",
  gallery: "🖼️",
  landmark: "🏰",
  monument: "🗿",
  viewpoint: "🌅",
  religious: "⛪",
  park: "🌳",
  culture: "🎭",
  market: "🧺",
  attraction: "🎡",
};

/** Stand-in picture for places without a photo. */
export function categoryIcon(slug: string): string {
  return CATEGORY_ICONS[slug] ?? "📍";
}

const WEEKDAYS: Record<string, string> = {
  Mo: "Mon",
  Tu: "Tue",
  We: "Wed",
  Th: "Thu",
  Fr: "Fri",
  Sa: "Sat",
  Su: "Sun",
  PH: "holidays",
};

/**
 * OpenStreetMap opening hours, made easier to read:
 * "Tu-Su 10:00-18:00; Jan 01,Dec 25 off" -> "Tue–Sun 10:00–18:00 · Jan 01, Dec 25 closed".
 * Shown as written otherwise; the syntax is too rich to evaluate here.
 */
export function formatOpeningHours(raw: string): string {
  if (raw.trim() === "24/7") return "Open 24/7";
  return raw
    .split(";")
    .map((rule) =>
      rule
        .trim()
        .replace(/\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b/g, (day) => WEEKDAYS[day])
        .replace(/(\w)-(\w)/g, "$1–$2")
        .replace(/,(?=\S)/g, ", ")
        .replace(/\b(off|closed)\b/g, "closed"),
    )
    .filter(Boolean)
    .join(" · ");
}

function names(places: { name: string }[]): string {
  return places.map((p) => p.name).join(", ");
}

/** "Day 2: replaced A, B with C, D." */
export function describeEdit(edit: PlanEdit): string {
  const replaced = `Day ${edit.day}: replaced ${names(edit.replaced)}`;
  return edit.added.length > 0
    ? `${replaced} with ${names(edit.added)}.`
    : `${replaced}; nothing else fits the day.`;
}

/** A change the planner made to a stop the traveller did not tick. */
export function describeAdjustment({ removed, added, reason }: Adjustment): string {
  if (removed && added) return `Also swapped ${removed.name} for ${added.name}. ${reason}`;
  if (added) return `Also added ${added.name}. ${reason}`;
  return `Also removed ${removed?.name ?? "a stop"}. ${reason}`;
}

/** An outdoor place the forecast left no room for, and what took its slot. */
export function describeWeatherSwap({ removed, added }: Adjustment): string {
  return `${added?.name ?? "An indoor place"} instead of ${removed?.name ?? "an outdoor one"}`;
}

const WEATHER_ICONS: Record<WeatherCondition, string> = {
  clear: "☀️",
  clouds: "☁️",
  fog: "🌫️",
  drizzle: "🌦️",
  rain: "🌧️",
  snow: "🌨️",
  thunderstorm: "⛈️",
};

/** Emoji for a forecast; OpenWeatherMap's icon code tells night ("01n") and how cloudy. */
export function weatherIcon({ condition, icon }: Pick<ForecastSlot, "condition" | "icon">): string {
  const night = icon.endsWith("n");
  if (condition === "clear") return night ? "🌙" : "☀️";
  if (condition === "clouds" && !night) {
    if (icon.startsWith("02")) return "🌤️"; // few clouds
    if (icon.startsWith("03")) return "⛅"; // scattered clouds
  }
  return WEATHER_ICONS[condition];
}

export function formatTemp(celsius: number): string {
  return `${Math.round(celsius)}°`;
}

/** "Wed 28 Oct" for "2026-10-28". The date is the city's own, so no time zone moves it. */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** "YYYY-MM-DD" of the day `days` after today, in the browser's time zone. */
export function localDate(days = 0, now: Date = new Date()): string {
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Outdoor stops that rain, fog or darkness still spoil. */
export function exposedStops(plan: PlanResponse): PlannedStop[] {
  return plan.days.flatMap((day) => day.stops.filter((stop) => stop.weather?.warning));
}

/** OpenWeatherMap's data needs a credit wherever it is shown. */
export function hasWeather(plan: PlanResponse): boolean {
  return plan.days.some((day) => day.weather);
}
