"use client";

import { useId } from "react";

import PlaceSearch from "@/components/PlaceSearch";
import type { PlaceRef } from "@/lib/types";

export const MAX_MUST_VISIT = 10;

export interface MustVisitPickerProps {
  value: PlaceRef[];
  onChange: (places: PlaceRef[]) => void;
  disabled?: boolean;
}

/** Search box for places that must be in the plan; picked places show as removable chips. */
export default function MustVisitPicker({ value, onChange, disabled }: MustVisitPickerProps) {
  const inputId = useId();
  const picked = new Set(value.map((p) => p.place_id));
  const full = value.length >= MAX_MUST_VISIT;

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-sm font-medium text-zinc-700">
        Must-visit places <span className="font-normal text-zinc-400">optional</span>
      </label>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Must-visit places">
          {value.map((place) => (
            <li
              key={place.place_id}
              className="flex items-center gap-1 rounded-full bg-amber-100 py-0.5 pr-1 pl-2.5 text-xs text-amber-900"
            >
              {place.name}
              <button
                type="button"
                onClick={() => onChange(value.filter((p) => p.place_id !== place.place_id))}
                disabled={disabled}
                aria-label={`Remove ${place.name}`}
                className="flex h-4 w-4 items-center justify-center rounded-full text-amber-700 hover:bg-amber-200"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <PlaceSearch
        inputId={inputId}
        exclude={picked}
        disabled={disabled || full}
        placeholder={full ? `Up to ${MAX_MUST_VISIT} places` : "Search, e.g. Jerónimos or castelo"}
        onPick={(place) => onChange([...value, { place_id: place.id, name: place.name }])}
      />
    </div>
  );
}
