"use client";

import Image from "next/image";
import { useState } from "react";

import {
  categoryIcon,
  categoryLabel,
  formatOpeningHours,
  formatTemp,
  weatherIcon,
} from "@/lib/format";
import type { PlannedStop } from "@/lib/types";

export interface StopCardProps {
  stop: PlannedStop;
  number: number;
  color: string;
  selected: boolean;
  onToggleSelected: () => void;
  selectionDisabled: boolean;
  /** Added by the last replacement. */
  isNew: boolean;
  /** Whether the traveller has been there; null for a plan not saved as a trip. */
  visited: boolean | null;
  /** Visits cannot change now: a draft of the trip is on screen. */
  visitLocked: boolean;
  onToggleVisited: () => void;
  /** The day is being edited: a Remove toggle instead of the tick for replacing. */
  editing: boolean;
  /** Marked to be taken out by the edit. */
  removed: boolean;
  onToggleRemoved: () => void;
  onHover: (placeId: number | null) => void;
}

// About two lines of the card's text column; longer descriptions get a More button.
const LONG_DESCRIPTION = 110;

function osmLink(lat: number, lon: number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=18/${lat}/${lon}`;
}

function Photo({ stop, number, color }: Pick<StopCardProps, "stop" | "number" | "color">) {
  const [broken, setBroken] = useState(false);
  const photo = broken ? null : stop.photo;
  return (
    <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-md bg-zinc-100 sm:h-28 sm:w-28">
      {photo ? (
        // Wikimedia serves sized thumbnails itself; loading them directly keeps the
        // attribution link honest and spares the Next.js image optimizer.
        <Image
          src={photo.url}
          alt={stop.name}
          width={224}
          height={224}
          unoptimized
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center text-4xl"
          style={{ background: `${color}14` }}
          aria-hidden
        >
          {categoryIcon(stop.category)}
        </div>
      )}
      <span
        className="absolute top-1.5 left-1.5 flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold text-white shadow ring-2 ring-white"
        style={{ background: color }}
      >
        {number}
      </span>
    </div>
  );
}

export default function StopCard({
  stop,
  number,
  color,
  selected,
  onToggleSelected,
  selectionDisabled,
  isNew,
  visited,
  visitLocked,
  onToggleVisited,
  editing,
  removed,
  onToggleRemoved,
  onHover,
}: StopCardProps) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article
      onMouseEnter={() => onHover(stop.place_id)}
      onMouseLeave={() => onHover(null)}
      className={`rounded-lg border bg-white p-2.5 shadow-sm transition ${
        removed
          ? "border-dashed border-zinc-300 opacity-60"
          : selected
            ? "border-blue-400 ring-2 ring-blue-500/20"
            : visited
              ? "border-emerald-300 bg-emerald-50/40"
              : "border-zinc-200 hover:border-zinc-300"
      }`}
    >
      <div className="flex gap-3">
        <Photo stop={stop} number={number} color={color} />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <h3
              className={`leading-snug font-medium text-zinc-900 ${removed ? "line-through" : ""}`}
            >
              {stop.name}
            </h3>
            {editing ? (
              !visited && (
                <button
                  type="button"
                  onClick={onToggleRemoved}
                  aria-pressed={removed}
                  aria-label={removed ? `Keep ${stop.name}` : `Take ${stop.name} out`}
                  className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${
                    removed
                      ? "bg-zinc-200 text-zinc-800 hover:bg-zinc-300"
                      : "border border-zinc-300 text-zinc-700 hover:border-red-400 hover:text-red-700"
                  }`}
                >
                  {removed ? "Keep" : "Remove"}
                </button>
              )
            ) : (
              <input
                type="checkbox"
                checked={selected}
                disabled={selectionDisabled || visited === true}
                onChange={onToggleSelected}
                aria-label={`Select ${stop.name} to replace`}
                title={visited ? "Visited places stay on the trip" : "Select to replace"}
                className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-blue-600"
              />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
            <span className="rounded bg-zinc-100 px-1.5 py-px font-medium text-zinc-700 tabular-nums">
              {stop.arrive}–{stop.leave}
            </span>
            <span>{categoryLabel(stop.category)}</span>
            {stop.weather && (
              <span title={`Forecast for ${stop.weather.time}: ${stop.weather.description}`}>
                {weatherIcon(stop.weather)} {formatTemp(stop.weather.temp_c)}
                {stop.weather.pop > 0 && ` · ${stop.weather.pop}%`}
              </span>
            )}
            {stop.outdoor && stop.weather && (
              <span className="rounded-full bg-sky-50 px-1.5 py-px font-medium text-sky-800">
                Outdoors
              </span>
            )}
            {stop.hours === "night" && (
              <span className="rounded-full bg-violet-100 px-1.5 py-px font-medium text-violet-800">
                🌙 Evening
              </span>
            )}
            {stop.must_visit && (
              <span className="rounded-full bg-amber-100 px-1.5 py-px font-medium text-amber-800">
                Must-visit
              </span>
            )}
            {isNew && (
              <span className="rounded-full bg-emerald-100 px-1.5 py-px font-medium text-emerald-800">
                New
              </span>
            )}
          </div>
          {stop.weather?.warning && (
            <p className="text-xs font-medium text-amber-700">⚠️ {stop.weather.warning}</p>
          )}
          {stop.note && <p className="text-xs text-blue-900">✨ {stop.note}</p>}
          {stop.description && (
            <p className="text-xs text-zinc-600">
              <span className={expanded ? "" : "line-clamp-2"}>{stop.description}</span>
              {stop.description.length > LONG_DESCRIPTION && (
                <button
                  type="button"
                  onClick={() => setExpanded((e) => !e)}
                  aria-expanded={expanded}
                  className="text-blue-600 hover:underline"
                >
                  {expanded ? "Less" : "More"}
                </button>
              )}
            </p>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
        {visited !== null && (
          <button
            type="button"
            onClick={onToggleVisited}
            disabled={visitLocked}
            aria-pressed={visited}
            className={`rounded-full px-2 py-0.5 font-medium disabled:cursor-not-allowed disabled:opacity-60 ${
              visited
                ? "bg-emerald-600 text-white hover:bg-emerald-700"
                : "border border-zinc-300 text-zinc-700 hover:border-emerald-500 hover:text-emerald-700"
            }`}
          >
            {visited ? "✓ Visited" : "Mark visited"}
          </button>
        )}
        {stop.opening_hours && <span>🕒 {formatOpeningHours(stop.opening_hours)}</span>}
        {stop.website && (
          <a
            href={stop.website}
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 hover:underline"
          >
            Website
          </a>
        )}
        <a
          href={osmLink(stop.lat, stop.lon)}
          target="_blank"
          rel="noreferrer"
          className="text-blue-600 hover:underline"
        >
          Map
        </a>
        {stop.photo?.credit && (
          <a
            href={stop.photo.page_url ?? undefined}
            target="_blank"
            rel="noreferrer"
            className="ml-auto max-w-full truncate text-[10px] text-zinc-400 hover:underline"
          >
            Photo: {stop.photo.credit}
          </a>
        )}
      </div>
    </article>
  );
}
