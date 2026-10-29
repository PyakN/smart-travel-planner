"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useEffectEvent, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import PlanForm from "@/components/PlanForm";
import PlanResult from "@/components/PlanResult";
import {
  ApiError,
  createPlan,
  editTripDay,
  getPlan,
  getTrip,
  markVisited,
  replaceStops,
  saveTrip,
  unmarkVisited,
  updateTrip,
} from "@/lib/api";
import { DEFAULT_DAY_END, DEFAULT_DAY_START, cityDate, cityNow, startingNow } from "@/lib/format";
import { authHref } from "@/lib/navigation";
import type { PlaceRef, PlanResponse, StartPoint, TravelMode, Trip, TripVisit } from "@/lib/types";

// Leaflet touches `window`, so the map only renders in the browser.
const RouteMap = dynamic(() => import("@/components/RouteMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-zinc-200" />,
});

type Status = { kind: "idle" } | { kind: "loading" } | { kind: "error"; message: string };

/** A saved trip and the account that opened it. */
interface OpenedTrip {
  trip: Trip;
  userId: number;
}

/** A change to a saved trip that it does not use until it is saved: a new plan version. */
interface Draft {
  tripId: number;
  plan: PlanResponse;
}

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function describeTripError(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "This trip does not exist, or it belongs to another account.";
  }
  return describe(error);
}

/** A saved plan's first day, unless it is past: then tomorrow, for planning it again. */
function upcoming(startDate: string | null): string {
  return startDate && startDate >= cityDate(0) ? startDate : cityDate(1);
}

/** A plan or trip id from the URL. */
function idParam(raw: string | null): number | null {
  return raw && /^\d+$/.test(raw) ? Number(raw) : null;
}

export default function Planner() {
  const params = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [opened, setOpened] = useState<OpenedTrip | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [text, setText] = useState("");
  const [start, setStart] = useState<StartPoint | null>(null);
  const [mustVisit, setMustVisit] = useState<PlaceRef[]>([]);
  const [modes, setModes] = useState<TravelMode[]>(["walk", "transit"]);
  const [startDate, setStartDate] = useState(() => cityDate(1));
  const [weatherAware, setWeatherAware] = useState(false);
  // The start the traveller picked; null for the default: 09:30, or now for a trip today.
  const [pickedStart, setPickedStart] = useState<string | null>(null);
  const [endTime, setEndTime] = useState(DEFAULT_DAY_END);
  const [laterStart, setLaterStart] = useState(DEFAULT_DAY_START);
  const [replacing, setReplacing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editingDay, setEditingDay] = useState(false);
  // Saving or discarding a draft, or undoing a change of the trip.
  const [applying, setApplying] = useState(false);
  // Why the last change to the plan or trip (replace, a draft, undo, a visit) failed.
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [selectedDay, setSelectedDay] = useState(1);
  const [highlightedStop, setHighlightedStop] = useState<number | null>(null);

  const sharedId = idParam(params.get("plan"));
  const tripId = idParam(params.get("trip"));
  const loadedId = plan?.id ?? null;
  const userId = user?.id ?? null;
  // The URL's trip, showing its current plan; trip mode only for the account that opened it.
  // A new plan or another link leaves trip mode, and so does logging out.
  const tripOnScreen =
    opened && opened.trip.id === tripId && opened.trip.plan.id === loadedId ? opened : null;
  const trip = tripOnScreen && tripOnScreen.userId === userId ? tripOnScreen.trip : null;
  // A draft of the trip on screen, made from its current version; it is shown instead of it.
  const tripDraft =
    trip && draft && draft.tripId === trip.id && draft.plan.parent_id === trip.plan.id
      ? draft.plan
      : null;
  const shown = tripDraft ?? plan;

  /** Show a saved plan, with its request in the form for planning it again. */
  const showSaved = useEffectEvent((saved: PlanResponse) => {
    setPlan(saved);
    setText(saved.request_text);
    setStart(saved.start);
    setMustVisit(saved.must_visit);
    setModes(saved.modes);
    setStartDate(upcoming(saved.start_date));
    setWeatherAware(saved.weather_aware);
    setPickedStart(saved.day_start === DEFAULT_DAY_START ? null : saved.day_start);
    setLaterStart(saved.day_start);
    setEndTime(saved.day_end);
    setSelectedDay(saved.edit?.day ?? 1);
    setEditError(null);
    setStatus({ kind: "idle" });
  });

  // Open a shared plan from ?plan=<id> (skipped for the plan we just created).
  useEffect(() => {
    if (sharedId === null || sharedId === loadedId) return;
    let cancelled = false;
    getPlan(sharedId)
      .then((saved) => {
        if (!cancelled) showSaved(saved);
      })
      .catch((error: unknown) => {
        if (!cancelled) setStatus({ kind: "error", message: describe(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [sharedId, loadedId]);

  /** A trip as read from the backend; the form is filled in only for a version not shown yet. */
  const showOpened = useEffectEvent((saved: Trip, owner: number) => {
    const shown = trip?.id === saved.id && loadedId === saved.plan.id;
    setOpened({ trip: saved, userId: owner });
    if (!shown) showSaved(saved.plan);
  });

  // Open the saved trip of ?trip=<id> once we know who is logged in. It is read again each
  // time the page is shown (Next.js keeps it hidden in between): it may have been renamed
  // or changed meanwhile.
  useEffect(() => {
    if (tripId === null || userId === null) return;
    let cancelled = false;
    getTrip(tripId)
      .then((saved) => {
        if (!cancelled) showOpened(saved, userId);
      })
      .catch((error: unknown) => {
        if (!cancelled) setStatus({ kind: "error", message: describeTripError(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [tripId, userId]);

  // Logged out with the trip on screen: its plan stays, as the public plan it is.
  const loggedOutOfTrip = tripOnScreen !== null && user === null;
  useEffect(() => {
    if (loggedOutOfTrip) window.history.replaceState(null, "", `?plan=${loadedId}`);
  }, [loggedOutOfTrip, loadedId]);
  // A trip link opened logged out: trips are private, so log in first.
  const tripNeedsLogIn = tripId !== null && user === null && !loggedOutOfTrip;

  /** Show the trip as the backend has it now, with its current plan. */
  function adopt(saved: Trip) {
    if (userId === null) return;
    setOpened({ trip: saved, userId });
    setPlan(saved.plan);
    setMustVisit(saved.plan.must_visit);
  }

  /** The plan on screen is saved: from now on it is shown as the trip. */
  function showTrip(saved: Trip) {
    adopt(saved);
    window.history.replaceState(null, "", `?trip=${saved.id}`);
  }

  /** Save the plan on screen to My trips; logged out, log in first and come back to save. */
  async function save() {
    if (!plan) return;
    if (!user) {
      router.push(authHref("/login", `/?plan=${plan.id}&save=1`));
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      showTrip(await saveTrip(plan.id));
    } catch (error) {
      setSaveError(describe(error));
    } finally {
      setSaving(false);
    }
  }

  // Back from logging in to save the plan (?plan=<id>&save=1). Saving twice gives the same
  // trip, so a repeated effect does no harm.
  const showTripOnReturn = useEffectEvent(showTrip);
  const saveRequested =
    params.get("save") === "1" && userId !== null && sharedId !== null && sharedId === loadedId;
  useEffect(() => {
    if (!saveRequested || sharedId === null) return;
    let cancelled = false;
    saveTrip(sharedId)
      .then((saved) => {
        if (!cancelled) showTripOnReturn(saved);
      })
      .catch((error: unknown) => {
        if (!cancelled) setSaveError(describe(error));
      });
    return () => {
      cancelled = true;
    };
  }, [saveRequested, sharedId]);

  // A trip that starts today starts now by default; the days after it keep their own start.
  const now = cityNow();
  const today = startDate === now.date;
  const startTime = pickedStart ?? (today ? startingNow(now.minutes) : DEFAULT_DAY_START);

  function changeStartDate(date: string) {
    // Starting today or not changes what the start time means: back to its default.
    if ((date === now.date) !== today) setPickedStart(null);
    setStartDate(date);
  }

  async function submit() {
    setStatus({ kind: "loading" });
    setPicking(false);
    try {
      const created = await createPlan({
        text: text.trim(),
        start,
        must_visit: mustVisit.map((p) => p.place_id),
        modes,
        start_date: startDate,
        weather_aware: weatherAware,
        day_start: today ? laterStart : startTime,
        day_end: endTime,
        first_day_start: today ? startTime : null,
      });
      setPlan(created);
      setSelectedDay(1);
      setEditError(null);
      setSaveError(null);
      setStatus({ kind: "idle" });
      window.history.replaceState(null, "", `?plan=${created.id}`);
    } catch (error) {
      setStatus({ kind: "error", message: describe(error) });
    }
  }

  async function replace(day: number, placeIds: number[]) {
    if (!plan) return;
    setReplacing(true);
    setEditError(null);
    try {
      const next = await replaceStops(plan.id, { day, place_ids: placeIds });
      if (trip) {
        // A draft: the trip moves on to it only once it is saved.
        setDraft({ tripId: trip.id, plan: next });
      } else {
        // Each replacement is a new plan version with its own link; Back (or Undo) returns
        // to the previous one.
        setPlan(next);
        window.history.pushState(null, "", `?plan=${next.id}`);
      }
      setSelectedDay(day);
    } catch (error) {
      setEditError(describe(error));
    } finally {
      setReplacing(false);
    }
  }

  /** Change a day of the trip (no AI); the result is a draft to save or discard. */
  async function editDay(day: number, change: { remove: number[]; add: number[] }) {
    if (!trip) return false;
    setEditingDay(true);
    setEditError(null);
    try {
      setDraft({ tripId: trip.id, plan: await editTripDay(trip.id, { day, ...change }) });
      setSelectedDay(day);
      return true;
    } catch (error) {
      setEditError(describe(error));
      return false;
    } finally {
      setEditingDay(false);
    }
  }

  /** Save the draft on screen: the trip uses it from now on (Undo goes back). */
  async function saveDraft() {
    if (!trip || !tripDraft) return;
    setApplying(true);
    setEditError(null);
    try {
      adopt(await updateTrip(trip.id, { plan_id: tripDraft.id }));
      setDraft(null);
    } catch (error) {
      setEditError(describe(error));
      // The trip changed meanwhile (another tab): show it as it is now, without the draft.
      if (error instanceof ApiError && error.status === 409) {
        await getTrip(trip.id)
          .then(adopt)
          .catch(() => undefined);
      }
    } finally {
      setApplying(false);
    }
  }

  /** Leave the trip as it is. The draft stays on the server, unused. */
  function discardDraft() {
    setDraft(null);
    setEditError(null);
  }

  async function undo() {
    if (!plan?.parent_id) return;
    setApplying(true);
    try {
      if (trip) {
        adopt(await updateTrip(trip.id, { plan_id: plan.parent_id }));
      } else {
        const previous = await getPlan(plan.parent_id);
        setPlan(previous);
        setMustVisit(previous.must_visit);
        window.history.pushState(null, "", `?plan=${previous.id}`);
      }
      setSelectedDay(plan.edit?.day ?? 1);
      setEditError(null);
    } catch (error) {
      setEditError(describe(error));
    } finally {
      setApplying(false);
    }
  }

  /** Tick a stop of the trip visited, or untick it; shown at once, undone if it fails. */
  async function toggleVisited(placeId: number, visited: boolean) {
    if (!trip) return;
    const tripId = trip.id;
    const changeVisits = (change: (visits: TripVisit[]) => TripVisit[]) =>
      setOpened((o) =>
        o && o.trip.id === tripId
          ? { ...o, trip: { ...o.trip, visits: change(o.trip.visits) } }
          : o,
      );
    const others = (visits: TripVisit[]) => visits.filter((v) => v.place_id !== placeId);
    setEditError(null);
    if (visited) {
      const name =
        plan?.days.flatMap((d) => d.stops).find((s) => s.place_id === placeId)?.name ?? "";
      changeVisits((v) => [...others(v), { place_id: placeId, name, visited_at: "" }]);
      try {
        const visit = await markVisited(tripId, placeId);
        changeVisits((v) => v.map((x) => (x.place_id === placeId ? visit : x)));
      } catch (error) {
        changeVisits(others);
        setEditError(describe(error));
      }
    } else {
      const visit = trip.visits.find((v) => v.place_id === placeId);
      changeVisits(others);
      try {
        await unmarkVisited(tripId, placeId);
      } catch (error) {
        if (visit) changeVisits((v) => [...others(v), visit]);
        setEditError(describe(error));
      }
    }
  }

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <main className="relative order-1 h-[42dvh] shrink-0 lg:order-2 lg:h-auto lg:flex-1">
        <RouteMap
          plan={shown}
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
              Plan your Lisbon trip
            </h1>
            <p className="text-sm text-zinc-500">
              An AI picks the places, an optimizer plans the walk.
            </p>
          </header>

          {tripNeedsLogIn && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
              This link opens a saved trip, which only its owner can see.{" "}
              <Link
                href={authHref("/login", `/?trip=${tripId}`)}
                className="font-medium underline hover:text-blue-950"
              >
                Log in
              </Link>{" "}
              to open it.
            </div>
          )}

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
            startDate={startDate}
            onStartDateChange={changeStartDate}
            weatherAware={weatherAware}
            onWeatherAwareChange={setWeatherAware}
            startTime={startTime}
            onStartTimeChange={setPickedStart}
            endTime={endTime}
            onEndTimeChange={setEndTime}
            laterStartTime={today ? laterStart : null}
            onLaterStartTimeChange={setLaterStart}
            nowMinutes={today ? now.minutes : null}
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

          {shown && (
            <PlanResult
              plan={shown}
              trip={trip}
              draft={tripDraft !== null}
              onSaveDraft={saveDraft}
              onDiscardDraft={discardDraft}
              applying={applying}
              onEditDay={trip ? editDay : null}
              editingDay={editingDay}
              onToggleVisited={toggleVisited}
              onSave={save}
              saving={saving}
              saveError={saveError}
              selectedDay={selectedDay}
              onSelectDay={setSelectedDay}
              onHoverStop={setHighlightedStop}
              onReplace={replace}
              replacing={replacing}
              editError={editError}
              onUndo={shown.parent_id && !tripDraft ? undo : null}
            />
          )}
        </div>
      </aside>
    </div>
  );
}
