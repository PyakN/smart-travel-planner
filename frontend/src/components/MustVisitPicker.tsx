"use client";

import { useEffect, useId, useState } from "react";

import { searchPlaces } from "@/lib/api";
import { categoryIcon, categoryLabel } from "@/lib/format";
import type { Place, PlaceRef } from "@/lib/types";

export const MAX_MUST_VISIT = 10;
const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

export interface MustVisitPickerProps {
  value: PlaceRef[];
  onChange: (places: PlaceRef[]) => void;
  disabled?: boolean;
}

interface Results {
  query: string;
  items: Place[];
}

/** Search box for places that must be in the plan; picked places show as removable chips. */
export default function MustVisitPicker({ value, onChange, disabled }: MustVisitPickerProps) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results>({ query: "", items: [] });
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const trimmed = query.trim();
  useEffect(() => {
    if (trimmed.length < MIN_QUERY) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchPlaces(trimmed, { signal: controller.signal })
        .then((page) => {
          setResults({ query: trimmed, items: page.items });
          setFailed(false);
          setActive(0);
        })
        .catch(() => {
          if (!controller.signal.aborted) setFailed(true);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  // Only results for what is typed now; places already picked are left out.
  const picked = new Set(value.map((p) => p.place_id));
  const options =
    trimmed.length >= MIN_QUERY && results.query === trimmed
      ? results.items.filter((p) => !picked.has(p.id))
      : [];
  const full = value.length >= MAX_MUST_VISIT;
  const showList = open && options.length > 0;

  function pick(place: Place) {
    onChange([...value, { place_id: place.id, name: place.name }]);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="space-y-2">
      <label htmlFor={`${listId}-input`} className="block text-sm font-medium text-zinc-700">
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

      <div className="relative">
        <input
          id={`${listId}-input`}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={`${listId}-list`}
          aria-autocomplete="list"
          aria-activedescendant={showList ? `${listId}-${active}` : undefined}
          value={query}
          disabled={disabled || full}
          placeholder={
            full ? `Up to ${MAX_MUST_VISIT} places` : "Search, e.g. Jerónimos or castelo"
          }
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
            } else if (showList && event.key === "ArrowDown") {
              event.preventDefault();
              setActive((i) => (i + 1) % options.length);
            } else if (showList && event.key === "ArrowUp") {
              event.preventDefault();
              setActive((i) => (i - 1 + options.length) % options.length);
            } else if (event.key === "Enter") {
              event.preventDefault(); // never submit the trip from here
              if (showList) pick(options[Math.min(active, options.length - 1)]);
            }
          }}
          className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:bg-zinc-50"
        />
        {showList && (
          <ul
            id={`${listId}-list`}
            role="listbox"
            className="absolute inset-x-0 top-full z-[1100] mt-1 max-h-64 overflow-y-auto rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
          >
            {options.map((place, i) => (
              <li
                key={place.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                // mousedown, not click: the input's blur would close the list first.
                onMouseDown={(event) => {
                  event.preventDefault();
                  pick(place);
                }}
                onMouseEnter={() => setActive(i)}
                className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 ${
                  i === active ? "bg-blue-50" : ""
                }`}
              >
                <span aria-hidden>{categoryIcon(place.category)}</span>
                <span className="min-w-0 flex-1 truncate text-zinc-900">{place.name}</span>
                <span className="shrink-0 text-xs text-zinc-400">
                  {categoryLabel(place.category)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {failed && <p className="text-xs text-red-600">Place search is unavailable right now.</p>}
    </div>
  );
}
