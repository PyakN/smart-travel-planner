import type { Adjustment, PlanEdit, PlannedStop } from "./types";

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

/** How the traveller reaches this stop, e.g. "Walk 11 min · 716 m". */
export function travelLabel(stop: PlannedStop): string | null {
  if (!stop.travel_mode) return null;
  const mode = stop.travel_mode === "transit" ? "Tram / metro" : "Walk";
  return `${mode} ${formatDuration(stop.travel_min)} · ${formatDistance(stop.distance_from_previous_m)}`;
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
