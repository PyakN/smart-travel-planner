"use client";

import { useEffect, useId, useState } from "react";

import { searchPlaces } from "@/lib/api";
import { categoryIcon, categoryLabel } from "@/lib/format";
import type { Place } from "@/lib/types";

const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

export interface PlaceSearchProps {
  /** The input's id, for a `<label htmlFor>`. */
  inputId: string;
  onPick: (place: Place) => void;
  /** Places not to offer: picked or planned already. */
  exclude?: ReadonlySet<number>;
  disabled?: boolean;
  placeholder: string;
}

interface Results {
  query: string;
  items: Place[];
}

/** Search box for places by name, with a list of matches to pick from by mouse or keyboard. */
export default function PlaceSearch({
  inputId,
  onPick,
  exclude,
  disabled,
  placeholder,
}: PlaceSearchProps) {
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

  // Only results for what is typed now.
  const options =
    trimmed.length >= MIN_QUERY && results.query === trimmed
      ? results.items.filter((p) => !exclude?.has(p.id))
      : [];
  const showList = open && options.length > 0;

  function pick(place: Place) {
    onPick(place);
    setQuery("");
    setOpen(false);
  }

  return (
    <>
      <div className="relative">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={`${listId}-list`}
          aria-autocomplete="list"
          aria-activedescendant={showList ? `${listId}-${active}` : undefined}
          value={query}
          disabled={disabled}
          placeholder={placeholder}
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
              event.preventDefault(); // never submit a form from here
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
    </>
  );
}
