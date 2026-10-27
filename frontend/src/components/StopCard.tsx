"use client";

import Image from "next/image";
import { useState } from "react";

import { categoryIcon, categoryLabel, formatOpeningHours } from "@/lib/format";
import type { PlannedStop } from "@/lib/types";

export interface StopCardProps {
  stop: PlannedStop;
  number: number;
  color: string;
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

export default function StopCard({ stop, number, color, onHover }: StopCardProps) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article
      onMouseEnter={() => onHover(stop.place_id)}
      onMouseLeave={() => onHover(null)}
      className="rounded-lg border border-zinc-200 bg-white p-2.5 shadow-sm transition hover:border-zinc-300"
    >
      <div className="flex gap-3">
        <Photo stop={stop} number={number} color={color} />
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="leading-snug font-medium text-zinc-900">{stop.name}</h3>
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
            <span>
              {categoryLabel(stop.category)} · {stop.arrive}–{stop.leave}
            </span>
            {stop.must_visit && (
              <span className="rounded-full bg-amber-100 px-1.5 py-px font-medium text-amber-800">
                Must-visit
              </span>
            )}
          </div>
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
