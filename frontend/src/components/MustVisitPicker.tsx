"use client";

import { useId } from "react";

import PlaceSearch from "@/components/PlaceSearch";
import { Label } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { placeSearchHint } from "@/lib/cities";
import type { PlaceRef } from "@/lib/types";

export const MAX_MUST_VISIT = 10;

export interface MustVisitPickerProps {
  /** The trip's city, a slug; null while it is not known (the search waits for it). */
  city: string | null;
  value: PlaceRef[];
  onChange: (places: PlaceRef[]) => void;
  disabled?: boolean;
}

/** A picked place: its name and a button to drop it. */
export function PlaceChip({
  name,
  removeLabel,
  onRemove,
  disabled,
}: {
  name: string;
  removeLabel: string;
  onRemove: () => void;
  disabled?: boolean;
}) {
  return (
    <li className="inline-flex h-8 max-w-full items-center gap-1 rounded-full border border-line-strong bg-surface pr-1 pl-3 text-small font-bold text-ink">
      <span className="truncate">{name}</span>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={removeLabel}
        className="flex size-6 shrink-0 items-center justify-center rounded-full text-ink-2 transition-colors hover:bg-canvas hover:text-ink"
      >
        <Icon name="x" size={14} />
      </button>
    </li>
  );
}

/** Search box for places that must be in the plan; picked places show as removable chips. */
export default function MustVisitPicker({ city, value, onChange, disabled }: MustVisitPickerProps) {
  const inputId = useId();
  const picked = new Set(value.map((p) => p.place_id));
  const full = value.length >= MAX_MUST_VISIT;

  return (
    <div className="space-y-2.5">
      <Label htmlFor={inputId} optional>
        Must-visit places
      </Label>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Must-visit places">
          {value.map((place) => (
            <PlaceChip
              key={place.place_id}
              name={place.name}
              removeLabel={`Remove ${place.name}`}
              onRemove={() => onChange(value.filter((p) => p.place_id !== place.place_id))}
              disabled={disabled}
            />
          ))}
        </ul>
      )}

      <PlaceSearch
        inputId={inputId}
        city={city ?? ""}
        exclude={picked}
        disabled={disabled || full || city === null}
        placeholder={full ? `Up to ${MAX_MUST_VISIT} places` : placeSearchHint(city)}
        onPick={(place) => onChange([...value, { place_id: place.id, name: place.name }])}
      />
    </div>
  );
}
