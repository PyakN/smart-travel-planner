"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import DayWeather from "@/components/DayWeather";
import PlaceSearch from "@/components/PlaceSearch";
import StopCard from "@/components/StopCard";
import {
  DEFAULT_DAY_END,
  DEFAULT_DAY_START,
  dayColor,
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
  formatTemp,
  freeEveningLabel,
  freeTimeLabel,
  hasWeather,
  rideBadge,
  rideDetails,
  textColorOn,
  transitCredits,
  travelLabel,
  weatherIcon,
} from "@/lib/format";
import type {
  DroppedStop,
  PlaceRef,
  PlanEdit,
  PlannedDay,
  PlannedStop,
  PlanResponse,
  TransitRide,
  Trip,
  VenueKind,
} from "@/lib/types";

export interface PlanResultProps {
  plan: PlanResponse;
  /** The saved trip this plan is the current version (or a draft) of; null for a plan not saved. */
  trip: Trip | null;
  /** The plan is a draft of the trip: shown, but not used by the trip until it is saved. */
  draft: boolean;
  onSaveDraft: () => void;
  onDiscardDraft: () => void;
  /** Saving a draft, or undoing a change of the trip. */
  applying: boolean;
  /** Change a day of the saved trip (take stops out, add places) into a draft; resolves to
   * whether it did. Null for a plan not saved. */
  onEditDay:
    ((day: number, change: { remove: number[]; add: number[] }) => Promise<boolean>) | null;
  /** The day edit is being planned. */
  editingDay: boolean;
  /** Search places to eat and drink for a day of the saved trip, around a stop (or where
   * the traveller is, by default). Null for a plan not saved. */
  onFindVenues: ((day: number, kind: VenueKind | null, near: PlannedStop | null) => void) | null;
  /** Tick a stop of the trip visited (true) or untick it. */
  onToggleVisited: (placeId: number, visited: boolean) => void;
  /** Save the plan to My trips. */
  onSave: () => void;
  saving: boolean;
  saveError: string | null;
  selectedDay: number;
  onSelectDay: (day: number) => void;
  onHoverStop: (placeId: number | null) => void;
  /** Replace the given stops of a day; the parent swaps in the new plan version (or a draft
   * of the trip). Resolves to whether it did. */
  onReplace: (day: number, placeIds: number[]) => Promise<boolean>;
  replacing: boolean;
  /** Why the last change to the plan failed. */
  editError: string | null;
  /** Go back to the version this plan was made from, if any. */
  onUndo: (() => void) | null;
}

function ShareButton({ planId }: { planId: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        // Share links open the plan, public and read-only, even for a saved trip.
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

function SaveButton({ trip, onSave, saving }: Pick<PlanResultProps, "trip" | "onSave" | "saving">) {
  if (trip) {
    return (
      <Link
        href="/trips"
        className="rounded-md px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
      >
        ✓ In My trips
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={onSave}
      disabled={saving}
      className="rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-wait disabled:bg-blue-400"
    >
      {saving ? "Saving…" : "Save to my trips"}
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

/**
 * Asks before saving a draft that drops planned stops, and says why each goes. Rendered on
 * the page's body: the draft bar's backdrop blur would make it the box `fixed` is relative to.
 */
function ConfirmDrop({
  dropped,
  onConfirm,
  onCancel,
}: {
  dropped: DroppedStop[];
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cancel = useEffectEvent(onCancel);
  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const stops = dropped.length === 1 ? "stop" : "stops";
  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-end justify-center bg-zinc-900/40 p-4 sm:items-center"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId} className="text-base font-semibold text-zinc-900">
          Drop {dropped.length} planned {stops}?
        </h2>
        <p className="mt-1 text-sm text-zinc-600">Saving this change takes them off the day:</p>
        <ul className="mt-3 space-y-2 text-sm">
          {dropped.map((stop) => (
            <li key={stop.place_id}>
              <span className="font-medium text-zinc-900">{stop.name}</span>
              <span className="block text-xs text-zinc-600">{stop.reason}</span>
            </li>
          ))}
        </ul>
        <div className="mt-5 flex justify-end gap-3">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="rounded-lg px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700"
          >
            Drop and save
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** A draft of the trip on screen: what it changes and drops, to save or discard. */
function DraftBar({
  edit,
  onSave,
  onDiscard,
  applying,
  error,
}: {
  edit: PlanEdit | null;
  onSave: () => void;
  onDiscard: () => void;
  applying: boolean;
  error: string | null;
}) {
  const [confirming, setConfirming] = useState(false);
  const dropped = edit?.dropped ?? [];
  return (
    <div
      role="region"
      aria-label="Draft"
      className="sticky bottom-0 -mx-4 space-y-1 border-t border-amber-200 bg-amber-50/95 px-4 py-3 text-sm shadow-[0_-4px_12px_rgba(0,0,0,0.05)] backdrop-blur lg:-mx-6 lg:px-6"
    >
      <p className="text-xs font-semibold tracking-wide text-amber-800 uppercase">
        Draft · not saved yet
      </p>
      {/* Long lists scroll: Save and Discard stay in view. */}
      <div className="max-h-[40dvh] space-y-1 overflow-y-auto">
        {edit && <p className="text-zinc-800">{describeEdit(edit)}</p>}
        {edit?.adjustments.map((a) => (
          <p key={`${a.removed?.place_id}-${a.added?.place_id}`} className="text-xs text-zinc-700">
            {describeAdjustment(a)}
          </p>
        ))}
        {dropped.length > 0 && (
          <div className="text-xs text-amber-900">
            <p className="font-medium">
              Drops {dropped.length} planned {dropped.length === 1 ? "stop" : "stops"}:
            </p>
            <ul className="list-disc pl-4">
              {dropped.map((stop) => (
                <li key={stop.place_id}>{describeDropped(stop)}</li>
              ))}
            </ul>
          </div>
        )}
        {edit?.warnings.map((w) => (
          <p key={w} className="text-xs text-amber-800">
            {w}
          </p>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-xs text-red-700">
          {error}
        </p>
      )}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="button"
          onClick={() => (dropped.length > 0 ? setConfirming(true) : onSave())}
          disabled={applying}
          className="flex-1 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:cursor-wait disabled:bg-emerald-400"
        >
          {applying ? "Saving…" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={onDiscard}
          disabled={applying}
          className="text-sm text-zinc-600 hover:text-zinc-900"
        >
          Discard
        </button>
      </div>
      {confirming && (
        <ConfirmDrop
          dropped={dropped}
          onConfirm={() => {
            setConfirming(false);
            onSave();
          }}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}

// The backend takes up to this many places to add in one edit.
const MAX_ADDED = 20;

/** Places to add to a day being edited: a search, and the ones picked so far. */
function AddPlaces({
  added,
  exclude,
  onAdd,
  onRemove,
  disabled,
}: {
  added: PlaceRef[];
  exclude: ReadonlySet<number>;
  onAdd: (place: PlaceRef) => void;
  onRemove: (placeId: number) => void;
  disabled: boolean;
}) {
  const inputId = useId();
  return (
    <div className="space-y-2 rounded-lg border border-dashed border-zinc-300 bg-white p-3">
      <label htmlFor={inputId} className="block text-sm font-medium text-zinc-700">
        Add a place
      </label>
      {added.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Places to add">
          {added.map((place) => (
            <li
              key={place.place_id}
              className="flex items-center gap-1 rounded-full bg-emerald-100 py-0.5 pr-1 pl-2.5 text-xs text-emerald-900"
            >
              {place.name}
              <button
                type="button"
                onClick={() => onRemove(place.place_id)}
                disabled={disabled}
                aria-label={`Do not add ${place.name}`}
                className="flex h-4 w-4 items-center justify-center rounded-full text-emerald-700 hover:bg-emerald-200"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <PlaceSearch
        inputId={inputId}
        exclude={exclude}
        disabled={disabled || added.length >= MAX_ADDED}
        placeholder="Search, e.g. Jerónimos or castelo"
        onPick={(place) => onAdd({ place_id: place.id, name: place.name })}
      />
      <p className="text-xs text-zinc-500">
        The day is planned again around your changes: visited stops stay first, and it may run until
        its end time.
      </p>
    </div>
  );
}

function WeatherNotes({ plan }: { plan: PlanResponse }) {
  const exposed = exposedStops(plan).length;
  if (plan.weather_swaps.length === 0 && exposed === 0) return null;
  return (
    <div className="mt-3 space-y-1 rounded-md bg-sky-50 p-2 text-xs text-sky-900">
      {plan.weather_swaps.length > 0 && (
        <>
          <p className="font-medium">Swapped for indoor places, as the forecast is wet or dark:</p>
          <ul className="list-disc pl-4">
            {plan.weather_swaps.map((swap) => (
              <li key={`${swap.removed?.place_id}-${swap.added?.place_id}`}>
                {describeWeatherSwap(swap)}
              </li>
            ))}
          </ul>
        </>
      )}
      {exposed > 0 && (
        <p>
          {exposed} outdoor {exposed === 1 ? "stop meets" : "stops meet"} rain, fog or darkness
          (marked ⚠️)
          {plan.weather_aware
            ? ": the forecast left no better slot."
            : ". Plan again with “Optimize route based on weather conditions” to rearrange."}
        </p>
      )}
    </div>
  );
}

function HoursNotes({ plan }: { plan: PlanResponse }) {
  if (plan.hours_swaps.length === 0) return null;
  return (
    <div className="mt-3 space-y-1 rounded-md bg-violet-50 p-2 text-xs text-violet-900">
      <p className="font-medium">Swapped for places that suit your hours:</p>
      <ul className="list-disc pl-4">
        {plan.hours_swaps.map((swap) => (
          <li key={`${swap.removed?.place_id}-${swap.added?.place_id}`}>
            {describeHoursSwap(swap)}
          </li>
        ))}
      </ul>
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
  visited,
  visitLocked,
  onToggleVisited,
  editing,
  removed,
  onToggleRemoved,
  onHoverStop,
  onFindVenues,
}: {
  day: PlannedDay;
  selected: number[];
  onToggle: (placeId: number) => void;
  locked: boolean;
  fresh: Set<number>;
  /** Visited stops of a saved trip; null for a plan not saved. */
  visited: Set<number> | null;
  visitLocked: boolean;
  onToggleVisited: PlanResultProps["onToggleVisited"];
  editing: boolean;
  /** Stops marked to be taken out by the day edit. */
  removed: number[];
  onToggleRemoved: (placeId: number) => void;
  onHoverStop: PlanResultProps["onHoverStop"];
  /** Search places to eat and drink near the day's last stop; null when it cannot. */
  onFindVenues: ((near: PlannedStop) => void) | null;
}) {
  const color = dayColor(day.day);
  const lastStop = day.stops.at(-1);
  const freeEvening = freeEveningLabel(day);
  return (
    <ol className="space-y-1">
      {day.stops.map((stop, i) => {
        const travel = travelLabel(stop);
        const freeTime = freeTimeLabel(stop);
        const departure = departureLabel(stop);
        return (
          <li key={stop.place_id}>
            {departure && (
              <p className="py-1 pl-[13px] text-xs font-medium text-zinc-600">
                <span aria-hidden>📍 </span>
                {departure}
              </p>
            )}
            {freeTime && (
              <p className="py-1 pl-[13px] text-xs text-zinc-500">
                <span aria-hidden>☕ </span>
                {freeTime}
              </p>
            )}
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
              visited={visited && visited.has(stop.place_id)}
              visitLocked={visitLocked}
              onToggleVisited={() => onToggleVisited(stop.place_id, !visited?.has(stop.place_id))}
              editing={editing}
              removed={removed.includes(stop.place_id)}
              onToggleRemoved={() => onToggleRemoved(stop.place_id)}
              onHover={onHoverStop}
            />
          </li>
        );
      })}
      {freeEvening && (
        <li className="py-1 pl-[13px] text-xs text-zinc-500">
          <span aria-hidden>🌙 </span>
          {freeEvening}
          {onFindVenues && lastStop && (
            <>
              {" · "}
              <button
                type="button"
                onClick={() => onFindVenues(lastStop)}
                className="font-medium text-blue-700 hover:text-blue-900 hover:underline"
              >
                Find places to eat &amp; drink
              </button>
            </>
          )}
        </li>
      )}
    </ol>
  );
}

export default function PlanResult({
  plan,
  trip,
  draft,
  onSaveDraft,
  onDiscardDraft,
  applying,
  onEditDay,
  editingDay,
  onFindVenues,
  onToggleVisited,
  onSave,
  saving,
  saveError,
  selectedDay,
  onSelectDay,
  onHoverStop,
  onReplace,
  replacing,
  editError,
  onUndo,
}: PlanResultProps) {
  const day = plan.days.find((d) => d.day === selectedDay) ?? plan.days[0];
  const city = plan.city.charAt(0).toUpperCase() + plan.city.slice(1);
  const title =
    trip?.title ?? `${plan.days.length} ${plan.days.length === 1 ? "day" : "days"} in ${city}`;
  const walking = plan.days.reduce((sum, d) => sum + d.walking_m, 0);
  const visited = trip ? new Set(trip.visits.map((v) => v.place_id)) : null;
  const transitLegs = plan.days.reduce((sum, d) => sum + d.transit_legs, 0);

  // Ticked stops belong to one day of one plan version; switching either clears them.
  const selectionKey = `${plan.id}:${day.day}`;
  const [picked, setPicked] = useState({ key: "", ids: [] as number[] });
  const visitedToday = day.stops.filter((s) => visited?.has(s.place_id)).length;
  // Visited stops stay on the trip: they cannot be replaced.
  const selected = (picked.key === selectionKey ? picked.ids : []).filter(
    (id) => !visited?.has(id),
  );
  const toggle = (placeId: number) =>
    setPicked({
      key: selectionKey,
      ids: selected.includes(placeId)
        ? selected.filter((id) => id !== placeId)
        : [...selected, placeId],
    });

  // Edit mode belongs to one day of one plan version too: a draft or another day ends it.
  const [edit, setEdit] = useState<{ key: string; remove: number[]; add: PlaceRef[] } | null>(null);
  const editing = edit !== null && edit.key === selectionKey ? edit : null;
  const planned = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.place_id)));
  const canEdit = onEditDay !== null && !draft && !replacing && !applying;
  const changeEdit = (change: Partial<{ remove: number[]; add: PlaceRef[] }>) =>
    setEdit({ key: selectionKey, remove: [], add: [], ...editing, ...change });

  return (
    <section className="space-y-4" aria-label="Trip plan">
      <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {trip && (
              <p className="text-xs font-medium tracking-wide text-emerald-700 uppercase">
                Saved trip
                {draft && <span className="text-amber-700"> · draft</span>}
              </p>
            )}
            <h2 className="text-base font-semibold text-zinc-900">{title}</h2>
            <p className="text-sm text-zinc-600">
              {formatDistance(walking)} on foot
              {transitLegs > 0 &&
                ` · ${transitLegs} transit ${transitLegs === 1 ? "ride" : "rides"}`}
              {" · "}
              {plan.trip.pace} pace
              {(plan.day_start !== DEFAULT_DAY_START || plan.day_end !== DEFAULT_DAY_END) &&
                ` · ${plan.day_start}–${plan.day_end}`}
              {plan.weather_aware && " · planned with the weather"}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <SaveButton trip={trip} onSave={onSave} saving={saving} />
            <ShareButton planId={plan.id} />
          </div>
        </div>
        {saveError && (
          <p role="alert" className="mt-2 text-xs text-red-700">
            {saveError}
          </p>
        )}
        {plan.rationale && <p className="mt-3 text-sm text-zinc-700">{plan.rationale}</p>}
        <WeatherNotes plan={plan} />
        <HoursNotes plan={plan} />
        {plan.edit && !draft && <EditSummary edit={plan.edit} onUndo={onUndo} />}
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
              <div className="flex items-baseline justify-between gap-2 font-semibold">
                Day {d.day}
                {d.weather && (
                  <span className="text-xs font-normal" title={d.weather.description}>
                    {weatherIcon(d.weather)} {formatTemp(d.weather.temp_max_c)}
                  </span>
                )}
              </div>
              <div className={`text-xs ${active ? "text-white/80" : "text-zinc-500"}`}>
                {d.date && `${formatDate(d.date)} · `}
                {d.stops.length} stops · {formatDuration(d.duration_min)}
              </div>
            </button>
          );
        })}
      </div>

      <div className="space-y-2">
        <DayWeather day={day} weatherAware={plan.weather_aware} />
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs text-zinc-500">
            {formatDistance(day.walking_m)} on foot
            {day.transit_legs > 0 &&
              ` + ${day.transit_legs} ${day.transit_legs === 1 ? "ride" : "rides"}`}{" "}
            · {day.stops[0]?.arrive}–{day.stops.at(-1)?.leave}
            {visited && ` · ${visitedToday} of ${day.stops.length} visited`}
            {editing
              ? " · take stops out or add places, then apply"
              : !draft && " · tick stops to replace them"}
          </p>
          {canEdit && !editing && (
            <div className="flex shrink-0 gap-1.5">
              {onFindVenues && (
                <button
                  type="button"
                  onClick={() => onFindVenues(day.day, "food", null)}
                  className="rounded-md bg-orange-50 px-2 py-1 text-xs font-medium text-orange-800 hover:bg-orange-100"
                >
                  Find places to eat
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setPicked({ key: selectionKey, ids: [] });
                  changeEdit({});
                }}
                className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-200"
              >
                Edit day
              </button>
            </div>
          )}
        </div>
        <DayStops
          day={day}
          selected={selected}
          onToggle={toggle}
          locked={replacing || applying || draft}
          fresh={newStops(plan.edit, day.day)}
          visited={visited}
          visitLocked={applying || draft || editing !== null}
          onToggleVisited={onToggleVisited}
          editing={editing !== null}
          removed={editing?.remove ?? []}
          onToggleRemoved={(placeId) => {
            const remove = editing?.remove ?? [];
            changeEdit({
              remove: remove.includes(placeId)
                ? remove.filter((id) => id !== placeId)
                : [...remove, placeId],
            });
          }}
          onHoverStop={onHoverStop}
          onFindVenues={
            canEdit && !editing && onFindVenues ? (near) => onFindVenues(day.day, null, near) : null
          }
        />
        {editing && (
          <AddPlaces
            added={editing.add}
            exclude={new Set([...planned, ...editing.add.map((p) => p.place_id)])}
            onAdd={(place) => changeEdit({ add: [...editing.add, place] })}
            onRemove={(placeId) =>
              changeEdit({ add: editing.add.filter((p) => p.place_id !== placeId) })
            }
            disabled={editingDay}
          />
        )}
      </div>

      {draft && (
        <DraftBar
          edit={plan.edit}
          onSave={onSaveDraft}
          onDiscard={onDiscardDraft}
          applying={applying}
          error={editError}
        />
      )}

      {!draft && editing && onEditDay && (
        <div className="sticky bottom-0 -mx-4 border-t border-zinc-200 bg-white/95 px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)] backdrop-blur lg:-mx-6 lg:px-6">
          {editError && (
            <p role="alert" className="mb-2 text-xs text-red-700">
              {editError}
            </p>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={async () => {
                const change = { remove: editing.remove, add: editing.add.map((p) => p.place_id) };
                // The picks became a draft: Discard or Undo must not bring them back.
                if (await onEditDay(day.day, change)) setEdit(null);
              }}
              disabled={editingDay || (editing.remove.length === 0 && editing.add.length === 0)}
              className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {editingDay
                ? "Planning the day…"
                : describeDayChange(editing.remove.length, editing.add.length)}
            </button>
            <button
              type="button"
              onClick={() => setEdit(null)}
              disabled={editingDay}
              className="text-sm text-zinc-600 hover:text-zinc-900"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {!draft && !editing && (selected.length > 0 || editError) && (
        <div className="sticky bottom-0 -mx-4 border-t border-zinc-200 bg-white/95 px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)] backdrop-blur lg:-mx-6 lg:px-6">
          {editError && (
            <p role="alert" className="mb-2 text-xs text-red-700">
              {editError}
            </p>
          )}
          {selected.length > 0 && (
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={async () => {
                  // The ticks became a new version: Discard or Undo must not bring them back.
                  if (await onReplace(day.day, selected)) setPicked({ key: selectionKey, ids: [] });
                }}
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
        {hasWeather(plan) && (
          <p>
            Weather data ©{" "}
            <a
              href="https://openweathermap.org/"
              target="_blank"
              rel="noreferrer"
              className="hover:underline"
            >
              OpenWeather
            </a>
          </p>
        )}
      </div>
    </section>
  );
}
