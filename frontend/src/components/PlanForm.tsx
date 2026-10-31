"use client";

import { useEffect, useState, type ReactNode } from "react";

import MustVisitPicker from "@/components/MustVisitPicker";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Hint, INPUT_COMPACT, SELECT } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Switch, ToggleChip } from "@/components/ui/Toggle";
import {
  CITY_NAME,
  addDays,
  cityDate,
  clockTime,
  dayLengthLabel,
  eachDayHint,
  formatDate,
  hoursHint,
} from "@/lib/format";
import type { IconName } from "@/lib/icons";
import type { DayHours, PlaceRef, StartPoint, TravelMode } from "@/lib/types";

const EXAMPLES = [
  "2 days in Lisbon, first time here. Viewpoints, the castle, Belém and one great museum.",
  "A slow day with kids: parks, the aquarium and a couple of miradouros.",
  "One intense day of art: museums and galleries, no churches please.",
];

const LOADING_STEPS = [
  "Understanding your request…",
  "Choosing places…",
  "Optimizing the route…",
  "Drawing the map…",
];

const MAX_CHARS = 1000;
const MAX_DAYS = 7;

const MODES: { mode: TravelMode; label: string }[] = [
  { mode: "walk", label: "Walking" },
  { mode: "transit", label: "Public transit" },
];

function modesHint(modes: TravelMode[]): string {
  if (!modes.includes("transit")) return "Everything on foot, so the places stay close together.";
  if (!modes.includes("walk")) return "Metro, tram, bus or train for anything over 1 km.";
  return "Walk, and ride the metro, tram or bus when a leg over 2.5 km is faster that way.";
}

// The free OpenWeatherMap forecast reaches five days ahead.
const FORECAST_DAYS = 5;

function weatherHint(weatherAware: boolean, startDate: string): string {
  if (!weatherAware) return "Off: the plan ignores the weather, and no forecast is\u00a0fetched.";
  if (startDate > cityDate(FORECAST_DAYS - 1)) {
    return "No forecast that far ahead yet: the plan will go without it.";
  }
  return "Rain, snow, fog and poor visibility within your hours (and only those) send outdoor stops to drier hours, or swap them for museums, churches and market halls.";
}

export interface PlanFormProps {
  text: string;
  onTextChange: (text: string) => void;
  start: StartPoint | null;
  picking: boolean;
  onTogglePicking: () => void;
  onClearStart: () => void;
  onToggleRoundTrip: () => void;
  mustVisit: PlaceRef[];
  onMustVisitChange: (places: PlaceRef[]) => void;
  modes: TravelMode[];
  onModesChange: (modes: TravelMode[]) => void;
  /** First day of the trip, "YYYY-MM-DD". */
  startDate: string;
  onStartDateChange: (date: string) => void;
  weatherAware: boolean;
  onWeatherAwareChange: (weatherAware: boolean) => void;
  /** "HH:MM", the city's time: when the first day starts (today: from now on). */
  startTime: string;
  onStartTimeChange: (time: string) => void;
  /** "HH:MM": when every day ends; not after the start means the next morning. */
  endTime: string;
  onEndTimeChange: (time: string) => void;
  /** When the days after today start, for a trip that starts today; null otherwise. */
  laterStartTime: string | null;
  onLaterStartTimeChange: (time: string) => void;
  /** Minutes since midnight in the city, for a trip that starts today. */
  nowMinutes: number | null;
  /** The number of days picked; null: as many as the description says. */
  dayCount: number | null;
  onDayCountChange: (days: number | null) => void;
  /** Each day has its own hours (`dayHours`) instead of the shared start and end. */
  eachDay: boolean;
  onEachDayChange: (eachDay: boolean) => void;
  /** The hours of each of the `dayCount` days, day 1 first. */
  dayHours: DayHours[];
  onDayHoursChange: (index: number, change: Partial<DayHours>) => void;
  loading: boolean;
  onSubmit: () => void;
}

/** What the planner is doing, as four stops on a line. */
function LoadingSteps() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1)),
      1200,
    );
    return () => clearInterval(timer);
  }, []);
  return (
    <span className="flex items-center gap-3">
      <span className="flex items-center" aria-hidden>
        {LOADING_STEPS.map((_, i) => (
          <span key={i} className="flex items-center">
            {i > 0 && (
              <span
                className={cn(
                  "h-0.5 w-3 transition-colors duration-300",
                  i <= step ? "bg-ink" : "bg-ink/25",
                )}
              />
            )}
            <span
              className={cn(
                "size-2 rounded-full transition-colors duration-300",
                i <= step ? "bg-ink" : "bg-ink/25",
              )}
            />
          </span>
        ))}
      </span>
      <span role="status">{LOADING_STEPS[step]}</span>
    </span>
  );
}

/** A row of the settings panel: an icon in the margin, the setting beside it. */
function SettingRow({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <div className="flex gap-3 px-4 py-4">
      <Icon name={icon} size={20} className="mt-px text-ink-3" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** A small label above a compact input. */
function MiniField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block min-w-0 space-y-1.5">
      <span className="block text-small font-bold text-ink-2">{label}</span>
      {children}
    </label>
  );
}

function EachDayHours({
  startDate,
  days,
  onChange,
  disabled,
}: {
  startDate: string;
  days: DayHours[];
  onChange: (index: number, change: Partial<DayHours>) => void;
  disabled: boolean;
}) {
  return (
    <ol className="divide-y divide-line rounded-control border border-line">
      {days.map((hours, i) => (
        <li
          key={i}
          className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-3 py-2.5"
        >
          <div className="leading-tight">
            <div className="text-sm font-bold text-ink">
              Day {i + 1}{" "}
              <span className="font-normal text-ink-2">{formatDate(addDays(startDate, i))}</span>
            </div>
            <div className="text-meta text-ink-3 tabular-nums">{dayLengthLabel(hours)}</div>
          </div>
          <div className="flex items-center gap-1.5 text-ink-3">
            <input
              type="time"
              aria-label={`Day ${i + 1} start`}
              value={hours.start}
              required
              disabled={disabled}
              onChange={(event) => onChange(i, { start: event.target.value })}
              className={INPUT_COMPACT}
            />
            <span aria-hidden>–</span>
            <input
              type="time"
              aria-label={`Day ${i + 1} end`}
              value={hours.end}
              required
              disabled={disabled}
              onChange={(event) => onChange(i, { end: event.target.value })}
              className={INPUT_COMPACT}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}

export default function PlanForm({
  text,
  onTextChange,
  start,
  picking,
  onTogglePicking,
  onClearStart,
  onToggleRoundTrip,
  mustVisit,
  onMustVisitChange,
  modes,
  onModesChange,
  startDate,
  onStartDateChange,
  weatherAware,
  onWeatherAwareChange,
  startTime,
  onStartTimeChange,
  endTime,
  onEndTimeChange,
  laterStartTime,
  onLaterStartTimeChange,
  nowMinutes,
  dayCount,
  onDayCountChange,
  eachDay,
  onEachDayChange,
  dayHours,
  onDayHoursChange,
  loading,
  onSubmit,
}: PlanFormProps) {
  const canSubmit = text.trim().length > 0 && !loading;
  const perDay = eachDay && dayHours.length > 1;
  const perDayHint = perDay ? eachDayHint(dayHours) : null;
  const nowNote = nowMinutes !== null && ` It is ${clockTime(nowMinutes)} in ${CITY_NAME} now.`;

  return (
    <form
      className="space-y-7"
      aria-busy={loading}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
    >
      <div className="space-y-3">
        <label htmlFor="trip-text" className="block text-sm font-bold text-ink">
          Describe your trip
        </label>
        <div className="rounded-panel border border-field bg-surface transition-colors focus-within:border-ink hover:border-ink-3 has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ink">
          <textarea
            id="trip-text"
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && canSubmit) {
                onSubmit();
              }
            }}
            maxLength={MAX_CHARS}
            rows={4}
            placeholder="e.g. 2 days in Lisbon with kids, we love viewpoints and old churches"
            className="block min-h-28 w-full resize-y rounded-panel bg-transparent px-4 pt-3.5 pb-1 text-base leading-relaxed text-ink placeholder:text-ink-3 focus-visible:outline-none lg:text-[16px]"
          />
          <div className="flex items-center justify-between px-4 pt-1 pb-3 text-meta text-ink-3">
            <span className="tabular-nums">
              {text.length} / {MAX_CHARS}
            </span>
            <span className="hidden lg:inline">Ctrl + Enter to plan</span>
          </div>
        </div>

        <div role="group" aria-label="Example requests" className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              title={example}
              onClick={() => onTextChange(example)}
              className="h-8 max-w-full truncate rounded-full border border-line bg-canvas px-3 text-left text-small text-ink-2 transition-colors hover:border-ink-3 hover:bg-surface hover:text-ink"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      <section aria-labelledby="trip-settings" className="space-y-3">
        <h2 id="trip-settings" className="font-display text-[19px] font-semibold text-ink">
          Trip settings
        </h2>
        <div className="divide-y divide-line rounded-panel border border-line bg-surface">
          <SettingRow icon="bed">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-bold text-ink">
                  Start point (hotel)
                  {!start && <span className="ml-1.5 font-normal text-ink-3">optional</span>}
                </p>
                <Hint className="mt-0.5">
                  {start
                    ? "Set on the map. Each day starts here."
                    : "Without one, each day starts at its first stop."}
                </Hint>
              </div>
              <div className="flex shrink-0 gap-1.5">
                {start && !picking && (
                  <Button variant="quiet" size="sm" onClick={onClearStart}>
                    Clear
                  </Button>
                )}
                <Button
                  variant={picking ? "dark" : "secondary"}
                  size="sm"
                  icon="locate"
                  onClick={onTogglePicking}
                  aria-pressed={picking}
                >
                  {picking ? "Click the map…" : start ? "Move" : "Set on map"}
                </Button>
              </div>
            </div>
            {start && (
              <Switch
                checked={start.round_trip}
                onChange={onToggleRoundTrip}
                className="mt-3 border-t border-line pt-3"
              >
                Return to the start point every evening
              </Switch>
            )}
          </SettingRow>

          <SettingRow icon="star">
            <MustVisitPicker value={mustVisit} onChange={onMustVisitChange} disabled={loading} />
          </SettingRow>

          <SettingRow icon="walk">
            <fieldset className="min-w-0">
              <legend className="mb-2.5 text-sm font-bold text-ink">Getting around</legend>
              <div className="flex flex-wrap gap-2">
                {MODES.map(({ mode, label }) => {
                  const checked = modes.includes(mode);
                  return (
                    <ToggleChip
                      key={mode}
                      checked={checked}
                      // At least one mode stays on.
                      disabled={loading || (checked && modes.length === 1)}
                      onChange={() =>
                        onModesChange(
                          checked
                            ? modes.filter((m) => m !== mode)
                            : MODES.map((m) => m.mode).filter(
                                (m) => m === mode || modes.includes(m),
                              ),
                        )
                      }
                    >
                      {label}
                    </ToggleChip>
                  );
                })}
              </div>
              <Hint className="mt-2">{modesHint(modes)}</Hint>
            </fieldset>
          </SettingRow>

          <SettingRow icon="calendar">
            <fieldset className="min-w-0 space-y-3">
              <legend className="mb-2.5 text-sm font-bold text-ink">When</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                <MiniField label="First day">
                  <input
                    type="date"
                    value={startDate}
                    min={cityDate(0)}
                    required
                    disabled={loading}
                    onChange={(event) => onStartDateChange(event.target.value)}
                    className={cn(INPUT_COMPACT, "w-full")}
                  />
                </MiniField>
                <MiniField label="Days">
                  <select
                    value={dayCount ?? ""}
                    disabled={loading}
                    onChange={(event) =>
                      onDayCountChange(event.target.value ? Number(event.target.value) : null)
                    }
                    className={cn(SELECT, "w-full")}
                  >
                    <option value="">As described</option>
                    {Array.from({ length: MAX_DAYS }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>
                        {n === 1 ? "1 day" : `${n} days`}
                      </option>
                    ))}
                  </select>
                </MiniField>
              </div>
              {dayCount === null && (
                <Hint>
                  As many as your description says, or 1. Pick a number to give each day its own
                  hours.
                </Hint>
              )}
              {dayCount !== null && dayCount > 1 && (
                <Switch
                  checked={eachDay}
                  disabled={loading}
                  onChange={(event) => onEachDayChange(event.target.checked)}
                >
                  Different hours each day
                </Switch>
              )}
              {perDay ? (
                <>
                  <EachDayHours
                    startDate={startDate}
                    days={dayHours}
                    onChange={onDayHoursChange}
                    disabled={loading}
                  />
                  {(perDayHint || nowNote) && (
                    <Hint>
                      {perDayHint}
                      {nowNote}
                    </Hint>
                  )}
                </>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <MiniField label={laterStartTime === null ? "Start" : "Start today"}>
                      <input
                        type="time"
                        value={startTime}
                        required
                        disabled={loading}
                        onChange={(event) => onStartTimeChange(event.target.value)}
                        className={cn(INPUT_COMPACT, "w-full")}
                      />
                    </MiniField>
                    <MiniField label="End">
                      <input
                        type="time"
                        value={endTime}
                        required
                        disabled={loading}
                        onChange={(event) => onEndTimeChange(event.target.value)}
                        className={cn(INPUT_COMPACT, "w-full")}
                      />
                    </MiniField>
                  </div>
                  {laterStartTime !== null && (
                    <label className="flex items-center justify-between gap-3 text-sm text-ink">
                      Later days start at
                      <input
                        type="time"
                        value={laterStartTime}
                        required
                        disabled={loading}
                        onChange={(event) => onLaterStartTimeChange(event.target.value)}
                        className={INPUT_COMPACT}
                      />
                    </label>
                  )}
                  <Hint>
                    {hoursHint(startTime, endTime, laterStartTime)}
                    {nowNote}
                  </Hint>
                </>
              )}
            </fieldset>
          </SettingRow>

          <SettingRow icon="cloud-sun">
            <Switch
              checked={weatherAware}
              disabled={loading}
              onChange={(event) => onWeatherAwareChange(event.target.checked)}
              className="font-bold"
            >
              Optimize route based on weather conditions
            </Switch>
            <Hint className="mt-1.5">{weatherHint(weatherAware, startDate)}</Hint>
          </SettingRow>
        </div>
      </section>

      <div className="sticky bottom-0 z-10 -mx-5 border-t border-line bg-surface px-5 pt-3 pb-4 shadow-bar lg:-mx-8 lg:px-8">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          block
          disabled={!canSubmit}
          aria-busy={loading}
          className="aria-busy:disabled:cursor-wait aria-busy:disabled:opacity-100"
        >
          {loading ? <LoadingSteps /> : "Plan my trip"}
        </Button>
      </div>
    </form>
  );
}
