"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import PlanForm from "@/components/PlanForm";
import PlanResult from "@/components/PlanResult";
import { ApiError, createPlan, getPlan, replaceStops } from "@/lib/api";
import type { PlaceRef, PlanResponse, StartPoint, TravelMode } from "@/lib/types";

// Leaflet touches `window`, so the map only renders in the browser.
const RouteMap = dynamic(() => import("@/components/RouteMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-zinc-200" />,
});

type Status = { kind: "idle" } | { kind: "loading" } | { kind: "error"; message: string };

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

export default function Planner() {
  const planParam = useSearchParams().get("plan");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [text, setText] = useState("");
  const [start, setStart] = useState<StartPoint | null>(null);
  const [mustVisit, setMustVisit] = useState<PlaceRef[]>([]);
  const [modes, setModes] = useState<TravelMode[]>(["walk", "transit"]);
  const [replacing, setReplacing] = useState(false);
  const [replaceError, setReplaceError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [selectedDay, setSelectedDay] = useState(1);
  const [highlightedStop, setHighlightedStop] = useState<number | null>(null);

  // Open a shared plan from ?plan=<id> (skipped for the plan we just created).
  const sharedId = planParam && /^\d+$/.test(planParam) ? Number(planParam) : null;
  const loadedId = plan?.id ?? null;
  useEffect(() => {
    if (sharedId === null || sharedId === loadedId) return;
    let cancelled = false;
    getPlan(sharedId)
      .then((saved) => {
        if (cancelled) return;
        setPlan(saved);
        setText(saved.request_text);
        setStart(saved.start);
        setMustVisit(saved.must_visit);
        setModes(saved.modes);
        setSelectedDay(saved.edit?.day ?? 1);
        setReplaceError(null);
        setStatus({ kind: "idle" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setStatus({ kind: "error", message: describe(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [sharedId, loadedId]);

  async function submit() {
    setStatus({ kind: "loading" });
    setPicking(false);
    try {
      const created = await createPlan({
        text: text.trim(),
        start,
        must_visit: mustVisit.map((p) => p.place_id),
        modes,
      });
      setPlan(created);
      setSelectedDay(1);
      setReplaceError(null);
      setStatus({ kind: "idle" });
      window.history.replaceState(null, "", `?plan=${created.id}`);
    } catch (error) {
      setStatus({ kind: "error", message: describe(error) });
    }
  }

  // Each replacement is a new plan version with its own link; Back (or Undo) returns
  // to the previous one.
  async function replace(day: number, placeIds: number[]) {
    if (!plan) return;
    setReplacing(true);
    setReplaceError(null);
    try {
      const next = await replaceStops(plan.id, { day, place_ids: placeIds });
      setPlan(next);
      setSelectedDay(day);
      window.history.pushState(null, "", `?plan=${next.id}`);
    } catch (error) {
      setReplaceError(describe(error));
    } finally {
      setReplacing(false);
    }
  }

  async function undo() {
    if (!plan?.parent_id) return;
    try {
      const previous = await getPlan(plan.parent_id);
      setPlan(previous);
      setMustVisit(previous.must_visit);
      setSelectedDay(plan.edit?.day ?? 1);
      setReplaceError(null);
      window.history.pushState(null, "", `?plan=${previous.id}`);
    } catch (error) {
      setReplaceError(describe(error));
    }
  }

  return (
    <div className="flex h-dvh flex-col lg:flex-row">
      <main className="relative order-1 h-[42dvh] shrink-0 lg:order-2 lg:h-auto lg:flex-1">
        <RouteMap
          plan={plan}
          selectedDay={selectedDay}
          onSelectDay={setSelectedDay}
          start={start}
          picking={picking}
          onPick={(lat, lon) => {
            setStart({ lat, lon, round_trip: start?.round_trip ?? false });
            setPicking(false);
          }}
          highlightedStop={highlightedStop}
        />
        {picking && (
          <div className="pointer-events-none absolute inset-x-0 top-3 z-[1000] flex justify-center">
            <span className="rounded-full bg-zinc-900/85 px-3 py-1.5 text-xs text-white shadow">
              Click the map to set your start point
            </span>
          </div>
        )}
      </main>

      <aside className="order-2 min-h-0 flex-1 overflow-y-auto border-zinc-200 bg-zinc-50 lg:order-1 lg:w-[440px] lg:flex-none lg:border-r">
        <div className="space-y-5 p-4 lg:p-6">
          <header>
            <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
              Smart Travel Planner
            </h1>
            <p className="text-sm text-zinc-500">
              Lisbon · an AI picks the places, an optimizer plans the walk.
            </p>
          </header>

          <PlanForm
            text={text}
            onTextChange={setText}
            start={start}
            picking={picking}
            onTogglePicking={() => setPicking((p) => !p)}
            onClearStart={() => setStart(null)}
            onToggleRoundTrip={() => setStart((s) => (s ? { ...s, round_trip: !s.round_trip } : s))}
            mustVisit={mustVisit}
            onMustVisitChange={setMustVisit}
            modes={modes}
            onModesChange={setModes}
            loading={status.kind === "loading"}
            onSubmit={submit}
          />

          {status.kind === "error" && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              {status.message}
            </div>
          )}

          {plan && (
            <PlanResult
              plan={plan}
              selectedDay={selectedDay}
              onSelectDay={setSelectedDay}
              onHoverStop={setHighlightedStop}
              onReplace={replace}
              replacing={replacing}
              replaceError={replaceError}
              onUndo={plan.parent_id ? undo : null}
            />
          )}
        </div>
      </aside>
    </div>
  );
}
