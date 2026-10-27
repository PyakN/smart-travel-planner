"use client";

import { useState } from "react";

import StopCard from "@/components/StopCard";
import {
  dayColor,
  describeAdjustment,
  describeEdit,
  formatDistance,
  formatDuration,
  rideBadge,
  rideDetails,
  textColorOn,
  transitCredits,
  travelLabel,
} from "@/lib/format";
import type { PlanEdit, PlannedDay, PlanResponse, TransitRide } from "@/lib/types";

export interface PlanResultProps {
  plan: PlanResponse;
  selectedDay: number;
  onSelectDay: (day: number) => void;
  onHoverStop: (placeId: number | null) => void;
  /** Replace the given stops of a day; the parent swaps in the new plan version. */
  onReplace: (day: number, placeIds: number[]) => void;
  replacing: boolean;
  replaceError: string | null;
  /** Go back to the version this plan was made from, if any. */
  onUndo: (() => void) | null;
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

function EditSummary({ edit, onUndo }: { edit: PlanEdit; onUndo: PlanResultProps["onUndo"] }) {
  return (
    <div className="mt-3 space-y-1 rounded-md bg-emerald-50 p-2 text-xs text-emerald-900">
      <div className="flex items-start justify-between gap-2">
        <p>{describeEdit(edit)}</p>
        {onUndo && (
          <button
            type="button"
            onClick={onUndo}
            className="shrink-0 font-medium text-emerald-800 underline hover:text-emerald-950"
          >
            Undo
          </button>
        )}
      </div>
      {edit.adjustments.map((a) => (
        <p key={`${a.removed?.place_id}-${a.added?.place_id}`}>{describeAdjustment(a)}</p>
      ))}
    </div>
  );
}

function Rides({ rides, color }: { rides: TransitRide[]; color: string }) {
  return (
    <ul className="space-y-0.5">
      {rides.map((ride, i) => {
        const background = ride.color ?? color;
        return (
          <li key={i} className="flex flex-wrap items-baseline gap-x-1.5">
            <span
              className="rounded px-1 py-px text-[11px] font-semibold"
              style={{ background, color: textColorOn(background) }}
            >
              {rideBadge(ride)}
            </span>
            <span>{rideDetails(ride)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function newStops(edit: PlanEdit | null, day: number): Set<number> {
  if (!edit || edit.day !== day) return new Set();
  const added = [...edit.added, ...edit.adjustments.flatMap((a) => (a.added ? [a.added] : []))];
  return new Set(added.map((p) => p.place_id));
}

function DayStops({
  day,
  selected,
  onToggle,
  locked,
  fresh,
  onHoverStop,
}: {
  day: PlannedDay;
  selected: number[];
  onToggle: (placeId: number) => void;
  locked: boolean;
  fresh: Set<number>;
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
              <div className="flex items-stretch gap-2 py-1 pl-[13px] text-xs text-zinc-500">
                <span
                  className={`min-h-5 border-l-2 ${stop.travel_mode === "transit" ? "border-dotted" : ""}`}
                  style={{ borderColor: color }}
                />
                <div className="space-y-0.5 py-0.5">
                  <div>{travel}</div>
                  {stop.rides.length > 0 && <Rides rides={stop.rides} color={color} />}
                </div>
              </div>
            )}
            <StopCard
              stop={stop}
              number={i + 1}
              color={color}
              selected={selected.includes(stop.place_id)}
              onToggleSelected={() => onToggle(stop.place_id)}
              selectionDisabled={locked}
              isNew={fresh.has(stop.place_id)}
              onHover={onHoverStop}
            />
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
  onReplace,
  replacing,
  replaceError,
  onUndo,
}: PlanResultProps) {
  const day = plan.days.find((d) => d.day === selectedDay) ?? plan.days[0];
  const walking = plan.days.reduce((sum, d) => sum + d.walking_m, 0);
  const transitLegs = plan.days.reduce((sum, d) => sum + d.transit_legs, 0);

  // Ticked stops belong to one day of one plan version; switching either clears them.
  const selectionKey = `${plan.id}:${day.day}`;
  const [picked, setPicked] = useState({ key: "", ids: [] as number[] });
  const selected = picked.key === selectionKey ? picked.ids : [];
  const toggle = (placeId: number) =>
    setPicked({
      key: selectionKey,
      ids: selected.includes(placeId)
        ? selected.filter((id) => id !== placeId)
        : [...selected, placeId],
    });

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
                ` · ${transitLegs} transit ${transitLegs === 1 ? "ride" : "rides"}`}
              {" · "}
              {plan.trip.pace} pace
            </p>
          </div>
          <ShareButton planId={plan.id} />
        </div>
        {plan.rationale && <p className="mt-3 text-sm text-zinc-700">{plan.rationale}</p>}
        {plan.edit && <EditSummary edit={plan.edit} onUndo={onUndo} />}
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
          {day.transit_legs > 0 &&
            ` + ${day.transit_legs} ${day.transit_legs === 1 ? "ride" : "rides"}`}{" "}
          · {day.stops[0]?.arrive}–{day.stops.at(-1)?.leave} · tick stops to replace them
        </p>
        <DayStops
          day={day}
          selected={selected}
          onToggle={toggle}
          locked={replacing}
          fresh={newStops(plan.edit, day.day)}
          onHoverStop={onHoverStop}
        />
      </div>

      {(selected.length > 0 || replaceError) && (
        <div className="sticky bottom-0 -mx-4 border-t border-zinc-200 bg-white/95 px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)] backdrop-blur lg:-mx-6 lg:px-6">
          {replaceError && (
            <p role="alert" className="mb-2 text-xs text-red-700">
              {replaceError}
            </p>
          )}
          {selected.length > 0 && (
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => onReplace(day.day, selected)}
                disabled={replacing}
                className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-wait disabled:bg-blue-400"
              >
                {replacing
                  ? "Finding new places…"
                  : `Replace ${selected.length} ${selected.length === 1 ? "stop" : "stops"}`}
              </button>
              <button
                type="button"
                onClick={() => setPicked({ key: selectionKey, ids: [] })}
                disabled={replacing}
                className="text-sm text-zinc-600 hover:text-zinc-900"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}

      <div className="space-y-0.5 text-[11px] text-zinc-400">
        <p>
          Plan #{plan.id} · distances: {plan.distance_source}
          {plan.transit_source && ` · transit: ${plan.transit_source}`} · planned in{" "}
          {((plan.timings_ms.total ?? 0) / 1000).toFixed(1)} s
        </p>
        {plan.transit_source && plan.transit_source !== "estimate" && (
          <p>
            Public transport routes © HERE
            {transitCredits(plan).map((credit) => (
              <span key={credit.text}>
                {" · "}
                {credit.url ? (
                  <a href={credit.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {credit.text}
                  </a>
                ) : (
                  credit.text
                )}
              </span>
            ))}
          </p>
        )}
      </div>
    </section>
  );
}
