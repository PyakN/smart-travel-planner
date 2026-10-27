"use client";

import { useEffect, useState } from "react";

import MustVisitPicker from "@/components/MustVisitPicker";
import type { PlaceRef, StartPoint, TravelMode } from "@/lib/types";

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

const MODES: { mode: TravelMode; label: string }[] = [
  { mode: "walk", label: "Walking" },
  { mode: "transit", label: "Public transit" },
];

function modesHint(modes: TravelMode[]): string {
  if (!modes.includes("transit")) return "Everything on foot, so the places stay close together.";
  if (!modes.includes("walk")) return "Tram, metro or train for anything over 1 km.";
  return "Walk, and take the tram or metro for legs over 2.5 km.";
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
  loading: boolean;
  onSubmit: () => void;
}

function LoadingSteps() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1)),
      1200,
    );
    return () => clearInterval(timer);
  }, []);
  return <span>{LOADING_STEPS[step]}</span>;
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
  loading,
  onSubmit,
}: PlanFormProps) {
  const canSubmit = text.trim().length > 0 && !loading;

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
    >
      <label htmlFor="trip-text" className="block text-sm font-medium text-zinc-700">
        Describe your trip
      </label>
      <textarea
        id="trip-text"
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && canSubmit) onSubmit();
        }}
        maxLength={MAX_CHARS}
        rows={4}
        placeholder="e.g. 2 days in Lisbon with kids, we love viewpoints and old churches"
        className="w-full resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
      />

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onTextChange(example)}
            className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-left text-xs text-zinc-600 hover:border-blue-300 hover:text-blue-700"
          >
            {example.length > 48 ? `${example.slice(0, 46)}…` : example}
          </button>
        ))}
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-3 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="text-zinc-700">
            <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-zinc-900 text-[11px] font-semibold text-white">
              H
            </span>
            {start ? "Start point set" : "Start point (hotel)"}
            <span className="ml-1 text-zinc-400">optional</span>
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onTogglePicking}
              aria-pressed={picking}
              className={`rounded-md px-2 py-1 text-xs font-medium ${
                picking ? "bg-blue-600 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
              }`}
            >
              {picking ? "Click the map…" : start ? "Move" : "Set on map"}
            </button>
            {start && (
              <button
                type="button"
                onClick={onClearStart}
                className="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-200"
              >
                Clear
              </button>
            )}
          </div>
        </div>
        {start && (
          <label className="mt-2 flex items-center gap-2 text-xs text-zinc-600">
            <input type="checkbox" checked={start.round_trip} onChange={onToggleRoundTrip} />
            Return to the start point every evening
          </label>
        )}
      </div>

      <MustVisitPicker value={mustVisit} onChange={onMustVisitChange} disabled={loading} />

      <fieldset className="rounded-lg border border-zinc-200 bg-white p-3 text-sm">
        <legend className="px-1 text-zinc-700">Getting around</legend>
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          {MODES.map(({ mode, label }) => {
            const checked = modes.includes(mode);
            return (
              <label key={mode} className="flex items-center gap-2 text-zinc-700">
                <input
                  type="checkbox"
                  checked={checked}
                  // At least one mode stays on.
                  disabled={loading || (checked && modes.length === 1)}
                  onChange={() =>
                    onModesChange(
                      checked
                        ? modes.filter((m) => m !== mode)
                        : MODES.map((m) => m.mode).filter((m) => m === mode || modes.includes(m)),
                    )
                  }
                />
                {label}
              </label>
            );
          })}
        </div>
        <p className="mt-1 text-xs text-zinc-500">{modesHint(modes)}</p>
      </fieldset>

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
      >
        {loading ? <LoadingSteps /> : "Plan my trip"}
      </button>
    </form>
  );
}
