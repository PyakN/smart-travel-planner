"use client";

import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { SELECT } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { cityNow, clockTime } from "@/lib/format";
import type { City } from "@/lib/types";

// Two rows of cards at most; past that, a select is quicker to scan.
const MAX_CARDS = 6;

/** The current time, refreshed every 20 s so the cities' clocks keep up. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

export interface CityPickerProps {
  /** The supported cities; null while they load. */
  cities: City[] | null;
  failed: boolean;
  onRetry: () => void;
  value: string | null;
  onChange: (slug: string) => void;
  disabled?: boolean;
}

/** Where the trip is: each city with its local time, like a departures board. */
export default function CityPicker({
  cities,
  failed,
  onRetry,
  value,
  onChange,
  disabled = false,
}: CityPickerProps) {
  const selectId = useId();
  const now = useNow();
  const localTime = (city: City) => clockTime(cityNow(city.timezone, now).minutes);

  if (failed) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-panel bg-canvas px-3.5 py-2.5 text-small text-ink-2">
        <span>Cities are unavailable right now, so the city comes from your request.</span>
        <Button size="sm" variant="quiet" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }

  if (!cities) {
    return (
      <div className="space-y-2.5" aria-busy="true" aria-label="Loading cities">
        <div className="h-5 w-12 animate-pulse rounded-tag bg-canvas" />
        <div className="grid grid-cols-3 gap-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-[62px] animate-pulse rounded-control bg-canvas" />
          ))}
        </div>
      </div>
    );
  }

  if (cities.length > MAX_CARDS) {
    return (
      <div className="space-y-2">
        <label htmlFor={selectId} className="block text-sm font-bold text-ink">
          City
        </label>
        <select
          id={selectId}
          value={value ?? ""}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          className={cn(SELECT, "h-11 w-full")}
        >
          {cities.map((city) => (
            <option key={city.slug} value={city.slug}>
              {city.name}, {localTime(city)} local time
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <fieldset className="min-w-0" disabled={disabled}>
      <legend className="mb-2.5 text-sm font-bold text-ink">City</legend>
      {/* Equal cards, every city in view: up to three to a row, more rows past that. */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(6.25rem,1fr))] gap-2">
        {cities.map((city) => {
          const checked = city.slug === value;
          return (
            <label
              key={city.slug}
              className={cn(
                "flex min-w-0 cursor-pointer flex-col gap-0.5 rounded-control border px-3 py-2.5 transition-colors select-none has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ink has-disabled:cursor-not-allowed has-disabled:opacity-55",
                checked
                  ? "border-ink bg-ink text-white"
                  : "border-line-strong bg-surface text-ink hover:border-ink-3",
              )}
            >
              <input
                type="radio"
                name="city"
                value={city.slug}
                checked={checked}
                onChange={() => onChange(city.slug)}
                className="sr-only"
              />
              <span className="truncate text-sm font-bold">{city.name}</span>
              <span
                className={cn(
                  "flex items-center justify-between gap-1 font-display text-[15px] leading-tight font-semibold tabular-nums",
                  checked ? "text-white/70" : "text-ink-3",
                )}
              >
                <span>
                  {localTime(city)}
                  <span className="sr-only"> local time</span>
                </span>
                {/* You are here: the chosen city carries the map pin. */}
                {checked && <Icon name="pin" size={15} className="text-signal" />}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
