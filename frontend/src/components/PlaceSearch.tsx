"use client";

import { useEffect, useId, useState } from "react";

import { cn } from "@/components/ui/cn";
import { INPUT } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { searchPlaces } from "@/lib/api";
import { categoryIcon, categoryLabel } from "@/lib/format";
import type { Place } from "@/lib/types";

const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

export interface PlaceSearchProps {
  /** The input's id, for a `<label htmlFor>`. */
  inputId: string;
  /** The city to search, a slug from GET /cities. */
  city: string;
  onPick: (place: Place) => void;
  /** Places not to offer: picked or planned already. */
  exclude?: ReadonlySet<number>;
  disabled?: boolean;
  placeholder: string;
}

interface Results {
  query: string;
  city: string;
  items: Place[];
}

/** Search box for places by name, with a list of matches to pick from by mouse or keyboard. */
export default function PlaceSearch({
  inputId,
  city,
  onPick,
  exclude,
  disabled,
  placeholder,
}: PlaceSearchProps) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results>({ query: "", city: "", items: [] });
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const trimmed = query.trim();
  useEffect(() => {
    if (trimmed.length < MIN_QUERY) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchPlaces(trimmed, city, { signal: controller.signal })
        .then((page) => {
          setResults({ query: trimmed, city, items: page.items });
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
  }, [trimmed, city]);

  // Only results for what is typed now, in the city searched now.
  const options =
    trimmed.length >= MIN_QUERY && results.query === trimmed && results.city === city
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
        <Icon
          name="search"
          size={18}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3"
        />
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
          className={cn(INPUT, "pl-10")}
        />
        {showList && (
          <ul
            id={`${listId}-list`}
            role="listbox"
            className="absolute inset-x-0 top-full z-[1100] mt-1.5 max-h-72 overflow-y-auto rounded-panel border border-line bg-surface p-1 shadow-float"
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
                className={cn(
                  "flex cursor-pointer items-center gap-2.5 rounded-control px-2.5 py-2 text-sm",
                  i === active && "bg-canvas",
                )}
              >
                <Icon name={categoryIcon(place.category)} size={18} className="text-ink-3" />
                <span className="min-w-0 flex-1 truncate font-bold text-ink">{place.name}</span>
                <span className="shrink-0 text-meta text-ink-3">
                  {categoryLabel(place.category)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {failed && (
        <p role="alert" className="text-small font-bold text-stop">
          Place search is unavailable right now.
        </p>
      )}
    </>
  );
}
