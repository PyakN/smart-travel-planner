"use client";

import Image from "next/image";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { Tag } from "@/components/ui/Tag";
import { Checkbox } from "@/components/ui/Toggle";
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
  /** The day's line colour, for the stand-in picture. */
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
  /** Picked up to move it to another place in the day: it floats above the others. */
  lifted?: boolean;
}

// About two lines of the card's text column; longer descriptions get a More button.
const LONG_DESCRIPTION = 110;

const LINK =
  "inline-flex items-center gap-1 rounded-tag text-small font-bold text-ink underline-offset-3 hover:underline";

function osmLink(lat: number, lon: number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=18/${lat}/${lon}`;
}

function Photo({ stop, color }: Pick<StopCardProps, "stop" | "color">) {
  const [broken, setBroken] = useState(false);
  const photo = broken ? null : stop.photo;
  return (
    <div className="relative size-16 shrink-0 overflow-hidden rounded-control bg-canvas sm:size-20">
      {photo ? (
        // Wikimedia serves sized thumbnails itself; loading them directly keeps the
        // attribution link honest and spares the Next.js image optimizer.
        <Image
          src={photo.url}
          alt={stop.name}
          width={176}
          height={176}
          unoptimized
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center"
          style={{ background: `color-mix(in srgb, ${color} 9%, white)`, color }}
          aria-hidden
        >
          <Icon name={categoryIcon(stop.category)} size={30} strokeWidth={1.5} />
        </div>
      )}
    </div>
  );
}

export default function StopCard({
  stop,
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
  lifted = false,
}: StopCardProps) {
  const [expanded, setExpanded] = useState(false);
  const tags = [
    stop.must_visit && (
      <Tag key="must" tone="signal" icon="star">
        Must-visit
      </Tag>
    ),
    isNew && (
      <Tag key="new" tone="go" icon="sparkle">
        New
      </Tag>
    ),
    stop.outdoor && stop.weather && (
      <Tag key="outdoor" tone="info" icon="tree">
        Outdoors
      </Tag>
    ),
    stop.hours === "night" && (
      <Tag key="evening" tone="evening" icon="moon">
        Evening
      </Tag>
    ),
  ].filter(Boolean);

  return (
    <article
      onMouseEnter={() => onHover(stop.place_id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        "rounded-panel border p-3 transition-[border-color,background-color,opacity,box-shadow] duration-200",
        lifted && "shadow-float",
        removed
          ? "border-dashed border-line-strong bg-surface opacity-55"
          : selected
            ? "border-ink bg-signal-soft"
            : "border-line bg-surface hover:border-line-strong",
      )}
    >
      <div className="flex gap-3">
        <div className="min-w-0 flex-1">
          {/* Phones have no time column beside the line: the times lead the card. */}
          <p className="mb-1 font-display text-[15px] leading-none font-semibold text-ink tabular-nums sm:hidden">
            {stop.arrive}
            <span className="font-normal text-ink-3">–{stop.leave}</span>
          </p>
          <div className="flex items-start justify-between gap-2">
            <h3
              className={cn(
                "text-base leading-snug font-bold text-ink",
                removed && "line-through decoration-2",
              )}
            >
              {stop.name}
            </h3>
            {editing ? (
              !visited && (
                <Button
                  variant={removed ? "dark" : "secondary"}
                  size="sm"
                  icon={removed ? "undo" : "x"}
                  onClick={onToggleRemoved}
                  aria-pressed={removed}
                  aria-label={removed ? `Keep ${stop.name}` : `Take ${stop.name} out`}
                  className="-mt-0.5 h-8 px-2.5"
                >
                  {removed ? "Keep" : "Remove"}
                </Button>
              )
            ) : (
              <Checkbox
                checked={selected}
                disabled={selectionDisabled || visited === true}
                onChange={onToggleSelected}
                aria-label={`Select ${stop.name} to replace`}
                title={visited ? "Visited places stay on the trip" : "Select to replace"}
                className="-m-1.5 p-1.5"
              />
            )}
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-ink-2">
            <span className="inline-flex items-center gap-1">
              <Icon name={categoryIcon(stop.category)} size={15} className="text-ink-3" />
              {categoryLabel(stop.category)}
            </span>
            {stop.weather && (
              <span
                className="inline-flex items-center gap-1 tabular-nums"
                title={`Forecast for ${stop.weather.time}: ${stop.weather.description}`}
              >
                <Icon name={weatherIcon(stop.weather)} size={15} className="text-ink-3" />
                {formatTemp(stop.weather.temp_c)}
                {stop.weather.pop > 0 && `, ${stop.weather.pop}% rain`}
              </span>
            )}
          </p>
          {tags.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{tags}</div>}
        </div>
        <Photo stop={stop} color={color} />
      </div>

      {stop.weather?.warning && (
        <p className="mt-2.5 flex gap-1.5 text-small font-bold text-caution">
          <Icon name="warning" size={16} className="mt-px" />
          {stop.weather.warning}
        </p>
      )}
      {stop.note && (
        <p className="mt-2.5 flex gap-2 rounded-control bg-canvas px-2.5 py-2 text-small text-ink">
          <Icon name="sparkle" size={16} className="mt-px text-ink-3" />
          <span>
            <span className="sr-only">Why it suits you: </span>
            {stop.note}
          </span>
        </p>
      )}
      {stop.description && (
        <p className="mt-2 text-small text-ink-2">
          <span className={expanded ? "" : "line-clamp-2"}>{stop.description}</span>
          {stop.description.length > LONG_DESCRIPTION && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              aria-expanded={expanded}
              className="font-bold text-ink underline-offset-3 hover:underline"
            >
              {expanded ? "Less" : "More"}
            </button>
          )}
        </p>
      )}
      {stop.opening_hours && (
        <p className="mt-2 flex gap-1.5 text-meta text-ink-2">
          <Icon name="clock" size={14} className="mt-px text-ink-3" />
          <span className="tabular-nums">{formatOpeningHours(stop.opening_hours)}</span>
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-2.5">
        {visited !== null && (
          <button
            type="button"
            onClick={onToggleVisited}
            disabled={visitLocked}
            aria-pressed={visited}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-small font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-55",
              visited
                ? "bg-go text-white enabled:hover:bg-go/90"
                : "border border-line-strong text-ink enabled:hover:border-go enabled:hover:text-go",
            )}
          >
            <Icon name="check" size={15} strokeWidth={visited ? 2.4 : 1.75} />
            {visited ? "Visited" : "Mark visited"}
          </button>
        )}
        {stop.website && (
          <a href={stop.website} target="_blank" rel="noreferrer" className={LINK}>
            <Icon name="globe" size={15} className="text-ink-3" />
            Website
          </a>
        )}
        <a href={osmLink(stop.lat, stop.lon)} target="_blank" rel="noreferrer" className={LINK}>
          <Icon name="map" size={15} className="text-ink-3" />
          Map
        </a>
        {stop.photo?.credit && (
          <a
            href={stop.photo.page_url ?? undefined}
            target="_blank"
            rel="noreferrer"
            className="ml-auto max-w-full truncate text-meta text-ink-3 hover:text-ink hover:underline"
          >
            Photo: {stop.photo.credit}
          </a>
        )}
      </div>
    </article>
  );
}
