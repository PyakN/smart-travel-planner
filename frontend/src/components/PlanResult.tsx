"use client";

import { useState } from "react";

import { categoryLabel, dayColor, formatDistance, formatDuration, travelLabel } from "@/lib/format";
import type { PlannedDay, PlanResponse } from "@/lib/types";

export interface PlanResultProps {
  plan: PlanResponse;
  selectedDay: number;
  onSelectDay: (day: number) => void;
  onHoverStop: (placeId: number | null) => void;
}

function osmLink(lat: number, lon: number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=18/${lat}/${lon}`;
}

function ShareButton({ planId }: { planId: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        const url = `${window.location.origin}/?plan=${planId}`;
        await navigator.clipboard.writeText(url).catch(() => undefined);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-200"
    >
      {copied ? "Link copied" : "Copy share link"}
    </button>
  );
}

function DayStops({
  day,
  onHoverStop,
}: {
  day: PlannedDay;
  onHoverStop: PlanResultProps["onHoverStop"];
}) {
  const color = dayColor(day.day);
  return (
    <ol className="space-y-1">
      {day.stops.map((stop, i) => {
        const travel = travelLabel(stop);
        return (
          <li key={stop.place_id}>
            {travel && (
              <div className="flex items-center gap-2 py-1 pl-[13px] text-xs text-zinc-500">
                <span
                  className={`h-5 border-l-2 ${stop.travel_mode === "transit" ? "border-dotted" : ""}`}
                  style={{ borderColor: color }}
                />
                {travel}
              </div>
            )}
            <div
              onMouseEnter={() => onHoverStop(stop.place_id)}
              onMouseLeave={() => onHoverStop(null)}
              className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white p-3 shadow-sm transition hover:border-zinc-300"
            >
              <span
                className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
                style={{ background: color }}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-zinc-900">{stop.name}</div>
                <div className="text-xs text-zinc-500">
                  {categoryLabel(stop.category)} · {stop.arrive}–{stop.leave}
                </div>
              </div>
              <a
                href={osmLink(stop.lat, stop.lon)}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-xs text-blue-600 hover:underline"
              >
                Map
              </a>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function PlanResult({
  plan,
  selectedDay,
  onSelectDay,
  onHoverStop,
}: PlanResultProps) {
  const day = plan.days.find((d) => d.day === selectedDay) ?? plan.days[0];
  const walking = plan.days.reduce((sum, d) => sum + d.walking_m, 0);
  const transitLegs = plan.days.reduce((sum, d) => sum + d.transit_legs, 0);

  return (
    <section className="space-y-4" aria-label="Trip plan">
      <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-zinc-900">
              {plan.days.length} {plan.days.length === 1 ? "day" : "days"} in{" "}
              {plan.city.charAt(0).toUpperCase() + plan.city.slice(1)}
            </h2>
            <p className="text-sm text-zinc-600">
              {formatDistance(walking)} on foot
              {transitLegs > 0 &&
                ` · ${transitLegs} tram/metro ${transitLegs === 1 ? "ride" : "rides"}`}
              {" · "}
              {plan.trip.pace} pace
            </p>
          </div>
          <ShareButton planId={plan.id} />
        </div>
        {plan.rationale && <p className="mt-3 text-sm text-zinc-700">{plan.rationale}</p>}
        {(plan.warnings.length > 0 || plan.dropped.length > 0) && (
          <div className="mt-3 rounded-md bg-amber-50 p-2 text-xs text-amber-800">
            {plan.dropped.length > 0 && (
              <p>Didn&apos;t fit the day: {plan.dropped.map((d) => d.name).join(", ")}.</p>
            )}
            {plan.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        )}
      </div>

      <div role="tablist" aria-label="Days" className="flex gap-2 overflow-x-auto pb-1">
        {plan.days.map((d) => {
          const active = d.day === day.day;
          return (
            <button
              key={d.day}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onSelectDay(d.day)}
              className={`shrink-0 rounded-lg border px-3 py-1.5 text-left text-sm ${
                active
                  ? "border-transparent text-white shadow"
                  : "border-zinc-200 bg-white text-zinc-700"
              }`}
              style={active ? { background: dayColor(d.day) } : undefined}
            >
              <div className="font-semibold">Day {d.day}</div>
              <div className={`text-xs ${active ? "text-white/80" : "text-zinc-500"}`}>
                {d.stops.length} stops · {formatDuration(d.duration_min)}
              </div>
            </button>
          );
        })}
      </div>

      <div>
        <p className="mb-2 text-xs text-zinc-500">
          {formatDistance(day.walking_m)} on foot
          {day.transit_legs > 0 && ` + ${day.transit_legs} tram/metro`} · {day.stops[0]?.arrive}–
          {day.stops.at(-1)?.leave}
        </p>
        <DayStops day={day} onHoverStop={onHoverStop} />
      </div>

      <p className="text-[11px] text-zinc-400">
        Plan #{plan.id} · distances: {plan.distance_source} · planned in{" "}
        {((plan.timings_ms.total ?? 0) / 1000).toFixed(1)} s
      </p>
    </section>
  );
}
