"use client";

import Link from "next/link";
import {
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import DayWeather from "@/components/DayWeather";
import ExportPanel from "@/components/ExportPanel";
import { PlaceChip } from "@/components/MustVisitPicker";
import PlaceSearch from "@/components/PlaceSearch";
import StopCard from "@/components/StopCard";
import { useReorder } from "@/components/useReorder";
import { Button, buttonClass } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Hint, Label } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import { Roundel } from "@/components/ui/Roundel";
import { Tag } from "@/components/ui/Tag";
import { placeSearchHint } from "@/lib/cities";
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
import type { IconName } from "@/lib/icons";
import { newOrder, onlyReordered, visitedLead } from "@/lib/reorder";
import type {
  DayEditRequest,
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

// The visited roundel's green.
const VISITED = "var(--color-go)";

export interface PlanResultProps {
  plan: PlanResponse;
  /** The plan's city, by name: "Berlin". */
  cityName: string;
  /** The saved trip this plan is the current version (or a draft) of; null for a plan not saved. */
  trip: Trip | null;
  /** The plan is a draft of the trip: shown, but not used by the trip until it is saved. */
  draft: boolean;
  onSaveDraft: () => void;
  onDiscardDraft: () => void;
  /** Saving a draft, or undoing a change of the trip. */
  applying: boolean;
  /** Change a day of the saved trip (take stops out, add places, put the stops in an order)
   * into a draft; resolves to whether it did. Null for a plan not saved. */
  onEditDay: ((day: number, change: Omit<DayEditRequest, "day">) => Promise<boolean>) | null;
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

/** A fact about the trip with its icon: "12.4 km on foot". */
function Stat({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon name={icon} size={16} className="text-ink-3" />
      {children}
    </span>
  );
}

function ShareButton({ planId }: { planId: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size="md"
      icon={copied ? "check" : "link"}
      onClick={async () => {
        // Share links open the plan, public and read-only, even for a saved trip.
        const url = `${window.location.origin}/?plan=${planId}`;
        await navigator.clipboard.writeText(url).catch(() => undefined);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
    >
      <span aria-live="polite">{copied ? "Link copied" : "Copy share link"}</span>
    </Button>
  );
}

function SaveButton({ trip, onSave, saving }: Pick<PlanResultProps, "trip" | "onSave" | "saving">) {
  if (trip) {
    return (
      <Link href="/trips" className={cn(buttonClass({ size: "md" }), "text-go")}>
        <Icon name="check" size={17} strokeWidth={2.2} />
        In My trips
      </Link>
    );
  }
  return (
    <Button variant="primary" size="md" onClick={onSave} disabled={saving} icon="star">
      {saving ? "Saving…" : "Save to my trips"}
    </Button>
  );
}

function EditSummary({ edit, onUndo }: { edit: PlanEdit; onUndo: PlanResultProps["onUndo"] }) {
  return (
    <Notice
      tone="go"
      icon="swap"
      title={describeEdit(edit)}
      action={
        onUndo && (
          <button
            type="button"
            onClick={onUndo}
            className="inline-flex shrink-0 items-center gap-1 font-bold text-ink underline-offset-3 hover:underline"
          >
            <Icon name="undo" size={15} />
            Undo
          </button>
        )
      }
    >
      {edit.adjustments.map((a) => (
        <p key={`${a.removed?.place_id}-${a.added?.place_id}`}>{describeAdjustment(a)}</p>
      ))}
      {edit.warnings.map((w) => (
        <p key={w}>{w}</p>
      ))}
    </Notice>
  );
}

/**
 * Asks before saving a draft that drops planned stops, and says why each goes. Rendered on
 * the page's body, above everything else.
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
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cancel = useEffectEvent(onCancel);
  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") cancel();
      // Tab stays within the dialog: from the last button back to the first, and back.
      if (event.key !== "Tab" || !dialogRef.current) return;
      const buttons = [...dialogRef.current.querySelectorAll<HTMLButtonElement>("button")];
      const [first, last] = [buttons[0], buttons.at(-1)];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const stops = dropped.length === 1 ? "stop" : "stops";
  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex animate-rise items-end justify-center bg-ink/45 p-4 sm:items-center"
      onClick={onCancel}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-panel bg-surface p-5 shadow-float"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId} className="font-display text-[22px] leading-tight font-semibold text-ink">
          Drop {dropped.length} planned {stops}?
        </h2>
        <p className="mt-1 text-sm text-ink-2">Saving this change takes them off the day:</p>
        <ul className="mt-4 divide-y divide-line rounded-control border border-line">
          {dropped.map((stop) => (
            <li key={stop.place_id} className="px-3 py-2.5">
              <span className="block text-sm font-bold text-ink">{stop.name}</span>
              <span className="block text-small text-ink-2">{stop.reason}</span>
            </li>
          ))}
        </ul>
        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className={buttonClass({ variant: "quiet" })}
          >
            Cancel
          </button>
          <Button variant="danger" onClick={onConfirm}>
            Drop and save
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** The bar at the bottom of the sidebar that holds the action for what is under way. */
function ActionBar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "sticky bottom-0 z-10 -mx-5 animate-rise border-t border-line bg-surface px-5 pt-3 pb-4 shadow-bar lg:-mx-8 lg:px-8",
        className,
      )}
    >
      {children}
    </div>
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
    <ActionBar className="space-y-2 border-t-caution/40">
      <div role="region" aria-label="Draft" className="space-y-2">
        <Tag tone="caution" icon="pencil">
          Draft, not saved yet
        </Tag>
        {/* Long lists scroll: Save and Discard stay in view. */}
        <div className="max-h-[36dvh] space-y-1.5 overflow-y-auto text-small">
          {edit && <p className="text-sm font-bold text-ink">{describeEdit(edit)}</p>}
          {edit?.adjustments.map((a) => (
            <p key={`${a.removed?.place_id}-${a.added?.place_id}`} className="text-ink-2">
              {describeAdjustment(a)}
            </p>
          ))}
          {dropped.length > 0 && (
            <div className="rounded-control bg-caution-soft px-3 py-2 text-ink">
              <p className="font-bold text-caution">
                Drops {dropped.length} planned {dropped.length === 1 ? "stop" : "stops"}:
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {dropped.map((stop) => (
                  <li key={stop.place_id}>{describeDropped(stop)}</li>
                ))}
              </ul>
            </div>
          )}
          {edit?.warnings.map((w) => (
            <p key={w} className="flex gap-1.5 text-caution">
              <Icon name="warning" size={15} className="mt-px" />
              {w}
            </p>
          ))}
        </div>
        {error && (
          <p role="alert" className="text-small font-bold text-stop">
            {error}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="primary"
          size="lg"
          block
          onClick={() => (dropped.length > 0 ? setConfirming(true) : onSave())}
          disabled={applying}
          className="flex-1"
        >
          {applying ? "Saving…" : "Save changes"}
        </Button>
        <Button variant="quiet" size="lg" onClick={onDiscard} disabled={applying}>
          Discard
        </Button>
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
    </ActionBar>
  );
}

// The backend takes up to this many places to add in one edit.
const MAX_ADDED = 20;

/** Places to add to a day being edited: a search, and the ones picked so far. */
function AddPlaces({
  city,
  added,
  exclude,
  onAdd,
  onRemove,
  disabled,
}: {
  /** The plan's city: places to add come from it. */
  city: string;
  added: PlaceRef[];
  exclude: ReadonlySet<number>;
  onAdd: (place: PlaceRef) => void;
  onRemove: (placeId: number) => void;
  disabled: boolean;
}) {
  const inputId = useId();
  return (
    <div className="space-y-2.5 rounded-panel border border-dashed border-line-strong bg-surface p-3.5">
      <Label htmlFor={inputId}>Add a place</Label>
      {added.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Places to add">
          {added.map((place) => (
            <PlaceChip
              key={place.place_id}
              name={place.name}
              removeLabel={`Do not add ${place.name}`}
              onRemove={() => onRemove(place.place_id)}
              disabled={disabled}
            />
          ))}
        </ul>
      )}
      <PlaceSearch
        inputId={inputId}
        city={city}
        exclude={exclude}
        disabled={disabled || added.length >= MAX_ADDED}
        placeholder={placeSearchHint(city)}
        onPick={(place) => onAdd({ place_id: place.id, name: place.name })}
      />
      <Hint>
        The day is planned again around your changes: visited stops stay first, and it may run until
        its end time.
      </Hint>
    </div>
  );
}

function WeatherNotes({ plan }: { plan: PlanResponse }) {
  const exposed = exposedStops(plan).length;
  if (plan.weather_swaps.length === 0 && exposed === 0) return null;
  return (
    <Notice tone="info" icon="rain">
      {plan.weather_swaps.length > 0 && (
        <>
          <p className="font-bold">Swapped for indoor places, as the forecast is wet or dark:</p>
          <ul className="list-disc space-y-0.5 pl-4">
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
          (marked with a warning)
          {plan.weather_aware
            ? ": the forecast left no better slot."
            : ". Plan again with “Optimize route based on weather conditions” to rearrange."}
        </p>
      )}
    </Notice>
  );
}

function HoursNotes({ plan }: { plan: PlanResponse }) {
  if (plan.hours_swaps.length === 0) return null;
  return (
    <Notice tone="evening" icon="clock" title="Swapped for places that suit your hours:">
      <ul className="list-disc space-y-0.5 pl-4">
        {plan.hours_swaps.map((swap) => (
          <li key={`${swap.removed?.place_id}-${swap.added?.place_id}`}>
            {describeHoursSwap(swap)}
          </li>
        ))}
      </ul>
    </Notice>
  );
}

function Rides({ rides, color }: { rides: TransitRide[]; color: string }) {
  return (
    <ul className="space-y-1">
      {rides.map((ride, i) => {
        const background = ride.color ?? color;
        return (
          <li key={i} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span
              className="inline-flex h-5 items-center rounded-tag px-1.5 font-display text-[13px] font-semibold"
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

// The itinerary's columns: times, the line, the stop (phones: the line and the stop).
const ROW =
  "grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2.5 sm:grid-cols-[2.75rem_1.75rem_minmax(0,1fr)]";
// Where the roundel's centre sits from the top of a stop row.
const ROUNDEL_CENTRE = "22px";
// Lines run a pixel past their row so the rows join without a seam.
const JOINED: CSSProperties = { top: -1, bottom: -1 };

/** A length of the day's line: solid on foot, dotted on a ride. */
function Line({
  color,
  dotted = false,
  className,
  style,
}: {
  color: string;
  dotted?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      aria-hidden
      className={cn("absolute left-1/2 w-1 -translate-x-1/2", className)}
      style={
        dotted
          ? {
              backgroundImage: `radial-gradient(circle, ${color} 1.9px, transparent 2.1px)`,
              backgroundSize: "4px 9px",
              backgroundRepeat: "repeat-y",
              backgroundPosition: "center top",
              ...style,
            }
          : { background: color, width: 3, ...style }
      }
    />
  );
}

/** A note on the line between stops: the walk, a ride, free time. */
function LineNote({
  icon,
  line,
  children,
  className,
}: {
  icon: IconName;
  /** The line beside the note; none where the day does not run (a free evening). */
  line: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn(ROW, "text-small text-ink-2")}>
      <span className="hidden sm:block" />
      <span className="relative">{line}</span>
      <div className={cn("flex gap-2 py-2.5", className)}>
        <Icon name={icon} size={16} className="mt-px text-ink-3" />
        <div className="min-w-0 flex-1 space-y-1">{children}</div>
      </div>
    </div>
  );
}

/** A planned day drawn as a transit line: times, the line in the day's colour, the stops. */
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
  onReorder,
  planning,
  focusStop,
  onFocused,
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
  /** Plan the day with its stops not visited in this order (`focus`: the stop whose handle
   * keeps the focus); null when they cannot move. */
  onReorder: ((order: number[], focus: number | null) => Promise<boolean>) | null;
  /** A change of the day is being planned. */
  planning: boolean;
  /** The stop moved with the keyboard last: its handle takes the focus, once. */
  focusStop: number | null;
  onFocused: () => void;
}) {
  const color = dayColor(day.day);
  const lastStop = day.stops.at(-1);
  const freeEvening = freeEveningLabel(day);
  const done = visited ?? new Set<number>();
  const movable = onReorder !== null && day.stops.filter((s) => !done.has(s.place_id)).length > 1;
  const instructionsId = useId();
  const [announcement, setAnnouncement] = useState("");
  const reorder = useReorder({
    count: day.stops.length,
    min: visitedLead(day.stops, done),
    onDrop: (from, to, keyboard) => {
      const order = newOrder(day.stops, done, from, to);
      const focus = keyboard ? day.stops[from].place_id : null;
      return order && onReorder ? onReorder(order, focus) : undefined;
    },
    announce: setAnnouncement,
    name: (i) => day.stops[i].name,
  });
  // The list comes back as a new plan: the handle moved with the keyboard keeps the focus.
  const list = useRef<HTMLOListElement>(null);
  const focused = useEffectEvent(onFocused);
  useEffect(() => {
    if (focusStop === null) return;
    list.current?.querySelector<HTMLElement>(`[data-stop="${focusStop}"]`)?.focus();
    focused();
  }, [focusStop]);
  return (
    <div>
      <ol
        ref={list}
        aria-busy={planning}
        className={cn(
          "motion-safe:animate-reveal-down",
          reorder.active && "select-none",
          planning && reorder.active && "opacity-70 transition-opacity",
        )}
      >
        {day.stops.map((stop, i) => {
          const travel = travelLabel(stop);
          const freeTime = freeTimeLabel(stop);
          const departure = departureLabel(stop);
          const isVisited = visited?.has(stop.place_id) ?? false;
          const lineBefore = i > 0 || travel !== null || freeTime !== null || departure !== null;
          const lineAfter = i < day.stops.length - 1;
          const moving = reorder.rowStyle(i);
          return (
            <li
              key={stop.place_id}
              ref={reorder.row(i)}
              style={moving.style}
              className={cn(
                moving.gliding && "motion-safe:transition-transform motion-safe:duration-200",
              )}
            >
              {departure && (
                <LineNote
                  icon="pin"
                  className="font-bold text-ink"
                  line={<Line color={color} style={{ top: "50%", bottom: -1 }} />}
                >
                  {departure}
                </LineNote>
              )}
              {freeTime && (
                <LineNote icon="coffee" line={<Line color={color} style={JOINED} />}>
                  {freeTime}
                </LineNote>
              )}
              {travel && (
                <LineNote
                  icon={stop.travel_mode === "transit" ? "transit" : "walk"}
                  line={
                    <Line color={color} dotted={stop.travel_mode === "transit"} style={JOINED} />
                  }
                >
                  <p>{travel}</p>
                  {stop.rides.length > 0 && <Rides rides={stop.rides} color={color} />}
                </LineNote>
              )}
              <div className={ROW}>
                <div className="hidden pt-[11px] text-right leading-none sm:block">
                  <span className="block font-display text-[15px] font-semibold text-ink tabular-nums">
                    {stop.arrive}
                  </span>
                  <span className="mt-1 block font-display text-[13px] text-ink-3 tabular-nums">
                    {stop.leave}
                  </span>
                </div>
                <div className="relative flex justify-center">
                  {lineBefore && (
                    <Line
                      color={color}
                      style={{ top: -1, height: `calc(${ROUNDEL_CENTRE} + 1px)` }}
                    />
                  )}
                  {lineAfter && <Line color={color} style={{ top: ROUNDEL_CENTRE, bottom: -1 }} />}
                  {movable && !isVisited ? (
                    // The roundel is the handle: a 44px target around it.
                    <button
                      type="button"
                      {...reorder.handle(i)}
                      data-stop={stop.place_id}
                      disabled={planning}
                      aria-label={`Move ${stop.name}, stop ${i + 1} of ${day.stops.length}`}
                      aria-describedby={instructionsId}
                      title="Drag to move this stop"
                      className="group relative -mx-2 cursor-grab touch-none self-start rounded-full p-2 select-none active:cursor-grabbing disabled:cursor-default"
                    >
                      <Roundel
                        color={color}
                        className={cn(
                          "motion-safe:transition-transform group-enabled:group-hover:scale-110",
                          reorder.moving === i && "scale-110",
                        )}
                      >
                        {i + 1}
                      </Roundel>
                    </button>
                  ) : (
                    <Roundel
                      color={isVisited ? VISITED : color}
                      className="relative mt-2 transition-colors"
                    >
                      {isVisited ? (
                        <Icon name="check" size={16} strokeWidth={2.6} label="Visited" />
                      ) : (
                        i + 1
                      )}
                    </Roundel>
                  )}
                </div>
                <div className="min-w-0 pb-1">
                  <StopCard
                    stop={stop}
                    color={color}
                    selected={selected.includes(stop.place_id)}
                    onToggleSelected={() => onToggle(stop.place_id)}
                    selectionDisabled={locked}
                    isNew={fresh.has(stop.place_id)}
                    visited={visited && isVisited}
                    visitLocked={visitLocked}
                    onToggleVisited={() => onToggleVisited(stop.place_id, !isVisited)}
                    editing={editing}
                    removed={removed.includes(stop.place_id)}
                    onToggleRemoved={() => onToggleRemoved(stop.place_id)}
                    onHover={onHoverStop}
                    lifted={moving.lifted}
                  />
                </div>
              </div>
            </li>
          );
        })}
        {freeEvening && (
          <li>
            <LineNote
              icon="moon"
              className="text-evening"
              line={
                <span className="absolute inset-x-0 top-2.5 flex justify-center" aria-hidden>
                  <span className="size-2.5 rounded-full border-2 border-evening bg-surface" />
                </span>
              }
            >
              <p className="font-bold">{freeEvening}</p>
              {onFindVenues && lastStop && (
                <button
                  type="button"
                  onClick={() => onFindVenues(lastStop)}
                  className="inline-flex items-center gap-1.5 font-bold text-ink underline-offset-3 hover:underline"
                >
                  <Icon name="utensils" size={15} />
                  Find places to eat &amp; drink
                </button>
              )}
            </LineNote>
          </li>
        )}
      </ol>
      {movable && (
        <p id={instructionsId} className="sr-only">
          Drag the stop&apos;s number up or down. Or press Space, move it with the arrow keys, and
          press Space again to drop it.
        </p>
      )}
      <p aria-live="assertive" className="sr-only">
        {announcement}
      </p>
    </div>
  );
}

/** Day tabs: a roundel, the date, and how full the day is. Arrow keys move between days. */
function DayTabs({
  days,
  active,
  onSelect,
  panelId,
  tabId,
}: {
  days: PlannedDay[];
  active: number;
  onSelect: (day: number) => void;
  panelId: string;
  tabId: (day: number) => string;
}) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = days.findIndex((d) => d.day === active);
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    let next: number | undefined;
    if (step !== undefined) next = days[(index + step + days.length) % days.length]?.day;
    if (event.key === "Home") next = days[0]?.day;
    if (event.key === "End") next = days.at(-1)?.day;
    if (next === undefined) return;
    event.preventDefault();
    onSelect(next);
    document.getElementById(tabId(next))?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Days"
      onKeyDown={onKeyDown}
      className="-mx-5 flex gap-2 overflow-x-auto px-5 py-1 [scrollbar-width:none] lg:-mx-8 lg:px-8"
    >
      {days.map((d) => {
        const selected = d.day === active;
        return (
          <button
            key={d.day}
            id={tabId(d.day)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={panelId}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(d.day)}
            className={cn(
              "flex shrink-0 items-center gap-2.5 rounded-panel border py-2 pr-4 pl-2 text-left transition-colors",
              selected
                ? "border-ink bg-surface"
                : "border-transparent bg-canvas hover:border-line-strong",
            )}
          >
            <Roundel color={dayColor(d.day)} size={30} ring={false}>
              {d.day}
            </Roundel>
            <span className="leading-tight">
              <span className="flex items-center gap-2 font-display text-[17px] font-semibold text-ink">
                Day {d.day}
                {d.weather && (
                  <span
                    className="inline-flex items-center gap-0.5 font-sans text-meta font-bold text-ink-2"
                    title={d.weather.description}
                  >
                    <Icon name={weatherIcon(d.weather)} size={15} />
                    {formatTemp(d.weather.temp_max_c)}
                  </span>
                )}
              </span>
              <span className="mt-0.5 block text-meta text-ink-2 tabular-nums">
                {d.date ? `${formatDate(d.date)}, ` : ""}
                {d.stops.length} stops
              </span>
              <span className="block text-meta text-ink-3 tabular-nums">
                {formatDuration(d.duration_min)}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default function PlanResult({
  plan,
  cityName,
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
  const ids = useId();
  const day = plan.days.find((d) => d.day === selectedDay) ?? plan.days[0];
  const title =
    trip?.title ?? `${plan.days.length} ${plan.days.length === 1 ? "day" : "days"} in ${cityName}`;
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
  // Stops move by dragging on a saved day, and again in a draft that only moved them.
  const reordered = draft && onlyReordered(plan.edit, day.day);
  const canReorder =
    onEditDay !== null &&
    (!draft || reordered) &&
    !replacing &&
    !applying &&
    !editing &&
    selected.length === 0;
  const changeEdit = (change: Partial<{ remove: number[]; add: PlaceRef[] }>) =>
    setEdit({ key: selectionKey, remove: [], add: [], ...editing, ...change });

  const panelId = `${ids}-panel`;
  const tabId = (n: number) => `${ids}-day-${n}`;
  const [exportOpen, setExportOpen] = useState(false);
  const [focusStop, setFocusStop] = useState<number | null>(null);
  const exportId = `${ids}-export`;

  return (
    <section className="space-y-6" aria-label="Trip plan">
      <header className="space-y-4">
        <div className="space-y-2">
          {(trip || draft) && (
            <div className="flex flex-wrap gap-1.5">
              {trip && (
                <Tag tone="go" icon="check">
                  Saved trip
                </Tag>
              )}
              {draft && (
                <Tag tone="caution" icon="pencil">
                  Draft
                </Tag>
              )}
            </div>
          )}
          <h2 className="font-display text-[26px] leading-[1.1] font-semibold text-balance text-ink lg:text-title">
            {title}
          </h2>
          <p className="flex flex-wrap gap-x-4 gap-y-1.5 text-small text-ink-2">
            <Stat icon="walk">{formatDistance(walking)} on foot</Stat>
            {transitLegs > 0 && (
              <Stat icon="transit">
                {transitLegs} transit {transitLegs === 1 ? "ride" : "rides"}
              </Stat>
            )}
            <Stat icon="gauge">
              {plan.trip.pace.charAt(0).toUpperCase() + plan.trip.pace.slice(1)} pace
            </Stat>
            {(plan.day_start !== DEFAULT_DAY_START || plan.day_end !== DEFAULT_DAY_END) && (
              <Stat icon="clock">
                <span className="tabular-nums">
                  {plan.day_start}–{plan.day_end}
                </span>
              </Stat>
            )}
            {plan.weather_aware && <Stat icon="cloud-sun">Planned with the weather</Stat>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <SaveButton trip={trip} onSave={onSave} saving={saving} />
          <ShareButton planId={plan.id} />
          <Button
            size="md"
            icon="download"
            aria-expanded={exportOpen}
            aria-controls={exportId}
            onClick={() => setExportOpen((open) => !open)}
          >
            Export
          </Button>
        </div>
        {exportOpen && <ExportPanel id={exportId} plan={plan} day={day} visited={visited} />}
        {saveError && (
          <p role="alert" className="text-small font-bold text-stop">
            {saveError}
          </p>
        )}
        {plan.ai_fallback ? (
          <Notice tone="caution" title="Planned without the AI" role="status">
            {plan.rationale && <p className="max-w-[65ch]">{plan.rationale}</p>}
          </Notice>
        ) : (
          plan.rationale && <p className="max-w-[65ch] text-body text-ink-2">{plan.rationale}</p>
        )}
        <WeatherNotes plan={plan} />
        <HoursNotes plan={plan} />
        {plan.edit && !draft && <EditSummary edit={plan.edit} onUndo={onUndo} />}
        {(plan.warnings.length > 0 || plan.dropped.length > 0) && (
          <Notice tone="caution">
            {plan.dropped.length > 0 && (
              <p>Didn&apos;t fit the day: {plan.dropped.map((d) => d.name).join(", ")}.</p>
            )}
            {plan.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </Notice>
        )}
      </header>

      <div className="space-y-4">
        <DayTabs
          days={plan.days}
          active={day.day}
          onSelect={onSelectDay}
          panelId={panelId}
          tabId={tabId}
        />

        <div id={panelId} role="tabpanel" aria-labelledby={tabId(day.day)} className="space-y-4">
          <DayWeather day={day} weatherAware={plan.weather_aware} />
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <p className="text-small text-ink-2">
              <span className="font-bold text-ink">{formatDistance(day.walking_m)}</span> on foot
              {day.transit_legs > 0 &&
                ` + ${day.transit_legs} ${day.transit_legs === 1 ? "ride" : "rides"}`}
              ,{" "}
              <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
                {day.stops[0]?.arrive}–{day.stops.at(-1)?.leave}
              </span>
              {visited && (
                <>
                  ,{" "}
                  <span className="font-bold text-go">
                    {visitedToday} of {day.stops.length} visited
                  </span>
                </>
              )}
            </p>
            {canEdit && !editing && (
              <div className="flex shrink-0 gap-2">
                {onFindVenues && (
                  <Button
                    size="sm"
                    icon="utensils"
                    onClick={() => onFindVenues(day.day, "food", null)}
                  >
                    Find places to eat
                  </Button>
                )}
                <Button
                  size="sm"
                  icon="pencil"
                  onClick={() => {
                    setPicked({ key: selectionKey, ids: [] });
                    changeEdit({});
                  }}
                >
                  Edit day
                </Button>
              </div>
            )}
          </div>
          {(editing || !draft || reordered) && (
            <p role="status" className="flex items-center gap-1.5 text-meta text-ink-3">
              <Icon name={editing ? "pencil" : canReorder ? "grip" : "swap"} size={14} />
              {editing
                ? "Take stops out or add places, then apply."
                : editingDay
                  ? "Planning the day in your order…"
                  : reordered
                    ? "Drag a stop by its number to move it again."
                    : canReorder
                      ? "Tick stops to replace them, or drag one by its number to move it."
                      : "Tick stops to replace them with new places."}
            </p>
          )}
          <DayStops
            key={selectionKey}
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
              canEdit && !editing && onFindVenues
                ? (near) => onFindVenues(day.day, null, near)
                : null
            }
            onReorder={
              canReorder && onEditDay
                ? (order, focus) => {
                    setFocusStop(focus);
                    return onEditDay(day.day, { order });
                  }
                : null
            }
            planning={editingDay}
            focusStop={editingDay ? null : focusStop}
            onFocused={() => setFocusStop(null)}
          />
          {editing && (
            <AddPlaces
              city={plan.city}
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
        <ActionBar>
          {editError && (
            <p role="alert" className="mb-2 text-small font-bold text-stop">
              {editError}
            </p>
          )}
          <div className="flex items-center gap-2">
            <Button
              variant="dark"
              size="lg"
              className="flex-1"
              onClick={async () => {
                const change = { remove: editing.remove, add: editing.add.map((p) => p.place_id) };
                // The picks became a draft: Discard or Undo must not bring them back.
                if (await onEditDay(day.day, change)) setEdit(null);
              }}
              disabled={editingDay || (editing.remove.length === 0 && editing.add.length === 0)}
            >
              {editingDay
                ? "Planning the day…"
                : describeDayChange(editing.remove.length, editing.add.length)}
            </Button>
            <Button variant="quiet" size="lg" onClick={() => setEdit(null)} disabled={editingDay}>
              Cancel
            </Button>
          </div>
        </ActionBar>
      )}

      {!draft && !editing && (selected.length > 0 || editError) && (
        <ActionBar>
          {editError && (
            <p role="alert" className="mb-2 text-small font-bold text-stop">
              {editError}
            </p>
          )}
          {selected.length > 0 && (
            <div className="flex items-center gap-2">
              <Button
                variant="dark"
                size="lg"
                icon="swap"
                className="flex-1"
                onClick={async () => {
                  // The ticks became a new version: Discard or Undo must not bring them back.
                  if (await onReplace(day.day, selected)) setPicked({ key: selectionKey, ids: [] });
                }}
                disabled={replacing}
              >
                {replacing
                  ? "Finding new places…"
                  : `Replace ${selected.length} ${selected.length === 1 ? "stop" : "stops"}`}
              </Button>
              <Button
                variant="quiet"
                size="lg"
                onClick={() => setPicked({ key: selectionKey, ids: [] })}
                disabled={replacing}
              >
                Clear
              </Button>
            </div>
          )}
        </ActionBar>
      )}

      <footer className="space-y-1 border-t border-line pt-4 text-meta text-ink-3">
        <p className="tabular-nums">
          Plan #{plan.id}, distances from {plan.distance_source}
          {plan.transit_source && `, transit from ${plan.transit_source}`}, planned in{" "}
          {((plan.timings_ms.total ?? 0) / 1000).toFixed(1)} s
        </p>
        {plan.transit_source && plan.transit_source !== "estimate" && (
          <p>
            Public transport routes © HERE
            {transitCredits(plan).map((credit) => (
              <span key={credit.text}>
                {", "}
                {credit.url ? (
                  <a
                    href={credit.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline-offset-3 hover:text-ink hover:underline"
                  >
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
              className="underline-offset-3 hover:text-ink hover:underline"
            >
              OpenWeather
            </a>
          </p>
        )}
      </footer>
    </section>
  );
}
