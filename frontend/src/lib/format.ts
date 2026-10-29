import type {
  Adjustment,
  Attribution,
  DayHours,
  DroppedStop,
  ForecastSlot,
  PlanEdit,
  PlannedDay,
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
  nightlife: "Bar & nightlife",
  restaurant: "Restaurant",
  cafe: "Café",
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
  nightlife: "🍸",
  restaurant: "🍽️",
  cafe: "☕",
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

/** "Day 2: replaced A, B with C, D.", or for a day edit "Day 2: took out A; added B (next)." */
export function describeEdit(edit: PlanEdit): string {
  if (edit.kind === "edit") {
    const next = edit.next;
    const added = edit.added.map((p) =>
      p.place_id === next?.place_id ? `${p.name} (next)` : p.name,
    );
    const parts = [];
    if (edit.removed.length > 0) parts.push(`took out ${names(edit.removed)}`);
    if (added.length > 0) parts.push(`added ${added.join(", ")}`);
    if (next && !edit.added.some((p) => p.place_id === next.place_id)) {
      parts.push(`${next.name} next`);
    }
    return `Day ${edit.day}: ${parts.join("; ") || "planned the rest of the day again"}.`;
  }
  const replaced = `Day ${edit.day}: replaced ${names(edit.replaced)}`;
  return edit.added.length > 0
    ? `${replaced} with ${names(edit.added)}.`
    : `${replaced}; nothing else fits the day.`;
}

/** The changes picked while editing a day, as its Apply button says them. */
export function describeDayChange(removed: number, added: number): string {
  const parts = [];
  if (removed > 0) parts.push(`take out ${removed} ${removed === 1 ? "stop" : "stops"}`);
  if (added > 0) parts.push(`add ${added} ${added === 1 ? "place" : "places"}`);
  const change = parts.join(" and ");
  return change ? change.charAt(0).toUpperCase() + change.slice(1) : "Nothing changed yet";
}

/** A planned stop a change leaves out: "Harbour Bar: The day would end at 23:10 instead of 21:30." */
export function describeDropped({ name, reason }: DroppedStop): string {
  return `${name}: ${reason}`;
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

/** A pick the day's hours had no room for, what took its slot, and why. */
export function describeHoursSwap({ removed, added, reason }: Adjustment): string {
  return `${added?.name ?? "Another place"} instead of ${removed?.name ?? "a pick"}: ${reason}`;
}

/** Plans are in the city's local time (Lisbon is the only city so far). */
export const CITY_TIME_ZONE = "Europe/Lisbon";
export const CITY_NAME = "Lisbon";
export const DEFAULT_DAY_START = "09:30";
export const DEFAULT_DAY_END = "21:30";
const MINUTES_PER_DAY = 24 * 60;

/** Today's date ("YYYY-MM-DD") and the time in minutes since midnight, in `timeZone`. */
export function cityNow(
  timeZone: string = CITY_TIME_ZONE,
  now: Date = new Date(),
): { date: string; minutes: number } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(now)
      .map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

/** "HH:MM" of minutes since midnight; the next morning's read like that day's. */
export function clockTime(minutes: number): string {
  const m = ((minutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
}

/** Minutes since midnight of "HH:MM". */
export function clockMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

/** When a trip that starts now starts: the next quarter of an hour, "HH:MM". */
export function startingNow(minutes: number): string {
  return clockTime(Math.ceil(minutes / 15) * 15);
}

/** Minutes from `start` to `end` ("HH:MM"); an end not after the start is the next morning. */
export function dayLength(start: string, end: string): number {
  const length = clockMinutes(end) - clockMinutes(start);
  return length > 0 ? length : length + MINUTES_PER_DAY;
}

const EVENING_NOTE =
  "After 20:00 the plan has a few lit squares and sights open late, and the rest of the evening is free: find places to eat and drink from your saved trip, or add them as must-visit places.";

/** Past 22:00 an evening is long enough to plan with places open at night. */
function lateEvening(start: string, end: string): boolean {
  return clockMinutes(end) < clockMinutes(start) || clockMinutes(end) > 22 * 60;
}

/**
 * A day's hours in a few words: "12 h a day", "11 h a day, until 03:00 the next morning".
 * With `laterStart`, `start` is today's (from now) and later days start then: whether the
 * end is the next morning goes by the days' own start, and today may be over already.
 */
export function hoursHint(start: string, end: string, laterStart: string | null = null): string {
  const dayStart = laterStart ?? start;
  if (dayStart === end) return "Pick an end time after the start.";
  const overnight = clockMinutes(end) < clockMinutes(dayStart);
  const length = clockMinutes(end) + (overnight ? MINUTES_PER_DAY : 0) - clockMinutes(start);
  if (length <= 0) return `Today's hours end at ${end}: start tomorrow, or end the day later.`;
  const days = laterStart === null ? "a day" : "today";
  const hint = overnight
    ? `${formatDuration(length)} ${days}, until ${end} the next morning.`
    : `${formatDuration(length)} ${days}.`;
  return lateEvening(dayStart, end) ? `${hint} ${EVENING_NOTE}` : hint;
}

/** How long a day of its own hours is: "8 h", "11 h, until the next morning". */
export function dayLengthLabel({ start, end }: DayHours): string {
  if (start === end) return "Pick an end after the start";
  const length = formatDuration(dayLength(start, end));
  return clockMinutes(end) < clockMinutes(start) ? `${length}, until the next morning` : length;
}

/** The hint under days that each have their own hours; null when there is nothing to say. */
export function eachDayHint(days: DayHours[]): string | null {
  if (days.some((d) => d.start === d.end)) return "Pick an end time after the start of every day.";
  for (let i = 1; i < days.length; i++) {
    const { start, end } = days[i - 1];
    const overnight = clockMinutes(end) < clockMinutes(start);
    if (overnight && clockMinutes(end) > clockMinutes(days[i].start)) {
      return `Day ${i} ends at ${end} the next day, after day ${i + 1} starts at ${days[i].start}.`;
    }
  }
  return days.some((d) => lateEvening(d.start, d.end)) ? EVENING_NOTE : null;
}

/** "16:00–03:00" for a day's hours; null on plans saved before days had hours. */
export function dayHours(day: { start: string | null; end: string | null }): string | null {
  return day.start && day.end ? `${day.start}–${day.end}` : null;
}

/** "From your location at 14:05", for a stop the day was re-planned to from there. */
export function departureLabel(stop: Pick<PlannedStop, "departure">): string | null {
  return stop.departure ? `From your location at ${stop.departure.time}` : null;
}

/** "Free time 1 h 25 min: it opens at 20:00", before a stop that opens later. */
export function freeTimeLabel(stop: Pick<PlannedStop, "wait_min" | "arrive">): string | null {
  if (stop.wait_min <= 0) return null;
  return `Free time ${formatDuration(stop.wait_min)}: it opens at ${stop.arrive}`;
}

/** "Free time from 21:40 until 03:00", after a day's last stop when its evening is free. */
export function freeEveningLabel(day: Pick<PlannedDay, "free_from" | "end">): string | null {
  if (!day.free_from) return null;
  return day.end
    ? `Free time from ${day.free_from} until ${day.end}`
    : `Free time from ${day.free_from}`;
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

/**
 * "YYYY-MM-DD" of the day `days` after today in the city: trip dates are the city's, so
 * "today" is Lisbon's today wherever the traveller's browser is.
 */
export function cityDate(days = 0, now: Date = new Date(), timeZone = CITY_TIME_ZONE): string {
  return addDays(cityNow(timeZone, now).date, days);
}

/** "YYYY-MM-DD" of the date `days` after `isoDate`. */
export function addDays(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

/** Outdoor stops that rain, fog or darkness still spoil. */
export function exposedStops(plan: PlanResponse): PlannedStop[] {
  return plan.days.flatMap((day) => day.stops.filter((stop) => stop.weather?.warning));
}

/** OpenWeatherMap's data needs a credit wherever it is shown. */
export function hasWeather(plan: PlanResponse): boolean {
  return plan.days.some((day) => day.weather);
}
