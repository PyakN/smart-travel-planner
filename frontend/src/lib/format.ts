import type { PlannedStop } from "./types";

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
