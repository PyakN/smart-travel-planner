"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { useCities } from "@/components/CitiesProvider";
import PlanForm from "@/components/PlanForm";
import PlanResult from "@/components/PlanResult";
import ProofCard from "@/components/ProofCard";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Notice";
import VenueSearch, { venueCardId } from "@/components/VenueSearch";
import {
  ApiError,
  createPlan,
  editTripDay,
  getPlan,
  getTrip,
  markVisited,
  replaceStops,
  replaceTripStops,
  saveTrip,
  unmarkVisited,
  updateTrip,
} from "@/lib/api";
import {
  browserTimeZone,
  cityName,
  conflictingCity,
  findCity,
  pickCity,
  storeCity,
  storedCity,
} from "@/lib/cities";
import {
  DEFAULT_DAY_END,
  DEFAULT_DAY_START,
  addDays,
  cityDate,
  cityNow,
  startingNow,
} from "@/lib/format";
import { authHref } from "@/lib/navigation";
import type {
  City,
  DayEditRequest,
  DayHours,
  PlaceRef,
  PlannedStop,
  PlanResponse,
  StartPoint,
  TravelMode,
  Trip,
  TripVisit,
  Venue,
  VenueKind,
} from "@/lib/types";
import {
  DEFAULT_RADIUS_M,
  type Placement,
  type SearchPoint,
  dayUnderWay,
  defaultSearchPoint,
  placements,
} from "@/lib/venues";

// Leaflet touches `window`, so the map only renders in the browser.
const RouteMap = dynamic(() => import("@/components/RouteMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-canvas" />,
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

/** A saved plan's first day, unless it is past in its city: then tomorrow, to plan it again. */
function upcoming(startDate: string | null, timeZone: string): string {
  return startDate && startDate >= cityDate(timeZone) ? startDate : cityDate(timeZone, 1);
}

/** What changing the city cleared, to put back with Undo. */
interface CitySwitch {
  from: City;
  start: StartPoint | null;
  mustVisit: PlaceRef[];
}

/** "your start point and 2 must-visit places". */
function clearedPlaces({ start, mustVisit }: CitySwitch): string {
  const places = mustVisit.length === 1 ? "place" : "places";
  return [
    start && "your start point",
    mustVisit.length > 0 && `${mustVisit.length} must-visit ${places}`,
  ]
    .filter(Boolean)
    .join(" and ");
}

/** A plan or trip id from the URL. */
function idParam(raw: string | null): number | null {
  return raw && /^\d+$/.test(raw) ? Number(raw) : null;
}

export default function Planner() {
  const params = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const { cities, failed: citiesFailed, retry: retryCities } = useCities();
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  // The city the traveller chose (or the one of the plan opened); null: not chosen yet.
  const [chosenCity, setChosenCity] = useState<string | null>(null);
  // The city chosen on this device last time.
  const [rememberedCity] = useState(storedCity);
  const [citySwitch, setCitySwitch] = useState<CitySwitch | null>(null);
  const [opened, setOpened] = useState<OpenedTrip | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  // With a plan on screen the request folds into one line; "Change" opens it again.
  const [formOpen, setFormOpen] = useState(false);
  const [proofHidden, setProofHidden] = useState(false);
  const [text, setText] = useState("");
  const [start, setStart] = useState<StartPoint | null>(null);
  const [mustVisit, setMustVisit] = useState<PlaceRef[]>([]);
  const [modes, setModes] = useState<TravelMode[]>(["walk", "transit"]);
  const [startDate, setStartDate] = useState(() => cityDate(browserTimeZone(), 1));
  const [weatherAware, setWeatherAware] = useState(false);
  // The start the traveller picked; null for the default: 09:30, or now for a trip today.
  const [pickedStart, setPickedStart] = useState<string | null>(null);
  const [endTime, setEndTime] = useState(DEFAULT_DAY_END);
  const [laterStart, setLaterStart] = useState(DEFAULT_DAY_START);
  // The number of days picked; null: as many as the description says.
  const [dayCount, setDayCount] = useState<number | null>(null);
  // Each day has its own hours: the shared ones until the traveller changes them (`ownHours`,
  // by day index).
  const [eachDay, setEachDay] = useState(false);
  const [ownHours, setOwnHours] = useState<Partial<DayHours>[]>([]);
  const [replacing, setReplacing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editingDay, setEditingDay] = useState(false);
  // Saving or discarding a draft, or undoing a change of the trip.
  const [applying, setApplying] = useState(false);
  // Why the last change to the plan or trip (replace, a draft, undo, a visit) failed.
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Picking a point on the map: the trip's start, or where the venue search looks.
  const [picking, setPicking] = useState<"start" | "venues" | null>(null);
  const [selectedDay, setSelectedDay] = useState(1);
  const [highlightedStop, setHighlightedStop] = useState<number | null>(null);
  // The venue search of a saved trip (?trip=<id>&eat=1): what it looks for and where (null:
  // the default point), and what it found.
  const [venueKind, setVenueKind] = useState<VenueKind | null>("food");
  const [venuePoint, setVenuePoint] = useState<SearchPoint | null>(null);
  const [radius, setRadius] = useState(DEFAULT_RADIUS_M);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [highlightedVenue, setHighlightedVenue] = useState<number | null>(null);
  // The search was opened from the route, so Back to route is the browser's Back.
  const pushedSearch = useRef(false);
  const sidebar = useRef<HTMLElement>(null);

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
  // Live editing needs a saved trip: the search is for trips only.
  const searching = trip !== null && shown !== null && params.get("eat") === "1";
  const searchDay = shown?.days.find((d) => d.day === selectedDay) ?? shown?.days[0];
  const searchPoint =
    venuePoint ??
    (trip && searchDay ? defaultSearchPoint(searchDay, trip.visits, shown?.start ?? null) : null);
  const pickingNow = picking === (searching ? "venues" : "start");

  // The city to plan for: the one chosen, the link's (?city=), the last one on this device,
  // or the first the backend lists. Dates and hours are in its time zone.
  const city = cities ? pickCity(cities, [chosenCity, params.get("city"), rememberedCity]) : null;
  const timeZone = city?.timezone ?? browserTimeZone();
  // The plan on screen has its own city, which the map, its clock and its searches follow.
  const planCity = shown ? findCity(cities, shown.city) : null;
  const planTimeZone = planCity?.timezone ?? timeZone;
  const conflict = cities ? conflictingCity(text, city, cities) : null;

  /** Show a saved plan, with its request in the form for planning it again. */
  const showSaved = useEffectEvent((saved: PlanResponse) => {
    setPlan(saved);
    setChosenCity(saved.city);
    setCitySwitch(null);
    setText(saved.request_text);
    setStart(saved.start);
    setMustVisit(saved.must_visit);
    setModes(saved.modes);
    setStartDate(upcoming(saved.start_date, findCity(cities, saved.city)?.timezone ?? timeZone));
    setWeatherAware(saved.weather_aware);
    setPickedStart(saved.day_start === DEFAULT_DAY_START ? null : saved.day_start);
    setLaterStart(saved.day_start);
    setEndTime(saved.day_end);
    setDayCount(saved.day_count);
    setEachDay(saved.day_hours.length > 0);
    setOwnHours(saved.day_hours);
    setSelectedDay(saved.edit?.day ?? 1);
    setEditError(null);
    setFormOpen(false);
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
  const now = cityNow(timeZone);
  const today = startDate === now.date;
  const startTime = pickedStart ?? (today ? startingNow(now.minutes) : DEFAULT_DAY_START);
  const dayHours: DayHours[] = Array.from({ length: dayCount ?? 0 }, (_, i) => ({
    start: ownHours[i]?.start ?? (i === 0 || !today ? startTime : laterStart),
    end: ownHours[i]?.end ?? endTime,
  }));
  const perDay = eachDay && dayHours.length > 1;

  function changeStartDate(date: string) {
    // Starting today or not changes what the start time means: back to its default.
    if ((date === now.date) !== today) {
      setPickedStart(null);
      setOwnHours(([first, ...rest]) => [{ ...first, start: undefined }, ...rest]);
    }
    setStartDate(date);
  }

  /** Plan for `next` from now on: remembered on this device, and in the link while no plan
   * has one. Dates follow its own today. */
  function chooseCity(next: City) {
    setChosenCity(next.slug);
    storeCity(next.slug);
    if (sharedId === null && tripId === null) {
      window.history.replaceState(null, "", `?city=${next.slug}`);
    }
    // A first day already past there moves to tomorrow; starting today or not changes what
    // the start time means.
    const cityToday = cityNow(next.timezone).date;
    const date = startDate < cityToday ? addDays(cityToday, 1) : startDate;
    if ((date === cityToday) !== today) {
      setPickedStart(null);
      setOwnHours(([first, ...rest]) => [{ ...first, start: undefined }, ...rest]);
    }
    setStartDate(date);
  }

  /** Switch the trip to another city. A start point and must-visit places belong to their
   * city (the backend refuses them in another), so they are cleared, and Undo puts them back. */
  function changeCity(slug: string) {
    const next = findCity(cities, slug);
    if (!next || next.slug === city?.slug) return;
    setCitySwitch(
      city && (start !== null || mustVisit.length > 0) ? { from: city, start, mustVisit } : null,
    );
    setStart(null);
    setMustVisit([]);
    setPicking(null);
    chooseCity(next);
  }

  function undoCitySwitch() {
    if (!citySwitch) return;
    chooseCity(citySwitch.from);
    setStart(citySwitch.start);
    setMustVisit(citySwitch.mustVisit);
    setCitySwitch(null);
  }

  function changeDayHours(index: number, change: Partial<DayHours>) {
    setOwnHours((hours) => {
      const changed = [...hours];
      changed[index] = { ...changed[index], ...change };
      return changed;
    });
  }

  async function submit() {
    setStatus({ kind: "loading" });
    setPicking(null);
    setCitySwitch(null);
    try {
      const created = await createPlan({
        text: text.trim(),
        city: city?.slug ?? null,
        start,
        must_visit: mustVisit.map((p) => p.place_id),
        modes,
        start_date: startDate,
        weather_aware: weatherAware,
        day_start: today ? laterStart : startTime,
        day_end: endTime,
        first_day_start: today && !perDay ? startTime : null,
        day_count: dayCount,
        day_hours: perDay ? dayHours : [],
      });
      setPlan(created);
      setSelectedDay(1);
      setEditError(null);
      setSaveError(null);
      setFormOpen(false);
      setStatus({ kind: "idle" });
      window.history.replaceState(null, "", `?plan=${created.id}`);
    } catch (error) {
      setStatus({ kind: "error", message: describe(error) });
    }
  }

  async function replace(day: number, placeIds: number[]) {
    if (!plan) return false;
    setReplacing(true);
    setEditError(null);
    try {
      const body = { day, place_ids: placeIds };
      // On a trip, the day's visited stops stay first.
      const next = await (trip ? replaceTripStops(trip.id, body) : replaceStops(plan.id, body));
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
      return true;
    } catch (error) {
      setEditError(describe(error));
      return false;
    } finally {
      setReplacing(false);
    }
  }

  /** Change a day of the trip (no AI); the result is a draft to save or discard. */
  async function editDay(day: number, change: Omit<DayEditRequest, "day">) {
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

  /** Search places to eat and drink for a day of the trip, around a stop or where the
   * traveller is (by default, the stop they visited last). */
  function openVenues(day: number, kind: VenueKind | null, near: PlannedStop | null) {
    if (!trip) return;
    setSelectedDay(day);
    setVenueKind(kind);
    setVenuePoint(
      near && {
        lat: near.lat,
        lon: near.lon,
        label: `${near.name}, the day's last stop`,
        stop: near.place_id,
      },
    );
    setVenues([]);
    setHighlightedVenue(null);
    setPicking(null);
    window.history.pushState(null, "", `?trip=${trip.id}&eat=1`);
    pushedSearch.current = true;
    sidebar.current?.scrollTo({ top: 0 });
  }

  function closeVenues() {
    setPicking(null);
    setHighlightedVenue(null);
    setEditError(null);
    if (pushedSearch.current) {
      pushedSearch.current = false;
      window.history.back();
    } else if (trip) {
      window.history.replaceState(null, "", `?trip=${trip.id}`);
    }
  }

  // Esc leaves the search (or stops pinning a point first), like Back to route.
  const onEscape = useEffectEvent(() => (picking ? setPicking(null) : closeVenues()));
  useEffect(() => {
    if (!searching) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onEscape();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [searching]);

  // A place to eat is the next stop: on a day under way, from where the traveller is now;
  // else right after the stop the search is around (the traveller may choose another).
  const liveSearch = searchDay ? dayUnderWay(searchDay, cityNow(planTimeZone)) : false;
  const venuePlacements =
    trip && searchDay
      ? placements(searchDay, trip.visits, shown?.start ?? null, searchPoint, liveSearch)
      : null;

  /** Re-plan the search's day with a venue (no AI): a draft that opens on the route. */
  async function addVenue(venue: Venue, stayMin: number, placement: Placement) {
    if (!searchDay) return false;
    const change: Omit<DayEditRequest, "day"> = {
      add: [venue.id],
      next: venue.id,
      after: placement.after?.place_id ?? null,
      stay_min: stayMin,
    };
    if (placement.fromHere && searchPoint) {
      change.start = { lat: searchPoint.lat, lon: searchPoint.lon };
    }
    const added = await editDay(searchDay.day, change);
    if (added) closeVenues();
    return added;
  }

  function selectVenue(venueId: number) {
    setHighlightedVenue(venueId);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document
      .getElementById(venueCardId(venueId))
      ?.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "nearest" });
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

  // Places on the trip already, by day: the search says so instead of adding them again.
  const plannedDays = new Map(
    (shown?.days ?? []).flatMap((d) => d.stops.map((s) => [s.place_id, d.day] as const)),
  );

  const formShown = shown === null || formOpen || status.kind !== "idle";

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <section
        aria-label="Map"
        className="relative order-1 h-[38dvh] shrink-0 lg:order-2 lg:h-auto lg:flex-1"
      >
        <RouteMap
          plan={shown}
          city={shown ? planCity : city}
          selectedDay={selectedDay}
          onSelectDay={setSelectedDay}
          start={start}
          picking={pickingNow}
          onPick={(lat, lon) => {
            if (picking === "venues") {
              setVenuePoint({ lat, lon, label: "the pin on the map", here: true });
            } else {
              setStart({ lat, lon, round_trip: start?.round_trip ?? false });
            }
            setPicking(null);
          }}
          highlightedStop={highlightedStop}
          venues={searching ? venues : []}
          search={searching && searchPoint ? { ...searchPoint, radius_m: radius } : null}
          highlightedVenue={highlightedVenue}
          onSelectVenue={selectVenue}
        />
        {pickingNow && (
          <div className="pointer-events-none absolute inset-x-0 top-3 z-[1000] flex justify-center px-3">
            <span className="inline-flex animate-rise items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-bold text-white shadow-float">
              <Icon name="locate" size={17} className="text-signal" />
              {searching ? "Click the map where you are" : "Click the map to set your start point"}
            </span>
          </div>
        )}
        {shown === null && !proofHidden && !pickingNow && (
          <ProofCard
            onDismiss={() => setProofHidden(true)}
            className="absolute bottom-8 left-6 z-[1000] hidden w-[340px] animate-rise lg:block"
          />
        )}
      </section>

      <main
        ref={sidebar}
        className="order-2 min-h-0 flex-1 overflow-y-auto bg-surface lg:order-1 lg:w-[480px] lg:flex-none lg:border-r lg:border-line"
      >
        {searching && searchDay && venuePlacements ? (
          <div className="px-5 pt-6 pb-8 lg:px-8 lg:pt-8">
            <VenueSearch
              day={searchDay}
              point={searchPoint}
              onPointChange={setVenuePoint}
              radius={radius}
              onRadiusChange={setRadius}
              picking={pickingNow}
              onTogglePicking={() => setPicking((p) => (p === "venues" ? null : "venues"))}
              initialKind={venueKind}
              onResults={setVenues}
              highlighted={highlightedVenue}
              onHover={setHighlightedVenue}
              planned={plannedDays}
              onBack={closeVenues}
              placements={venuePlacements}
              onAdd={addVenue}
              adding={editingDay}
              error={editError}
            />
          </div>
        ) : (
          <div className="space-y-6 px-5 pt-6 pb-8 lg:px-8 lg:pt-8">
            <header className={cn("space-y-2", !formShown && "sr-only")}>
              <h1 className="font-display text-[28px] leading-[1.05] font-semibold text-balance text-ink lg:text-display">
                Plan your{" "}
                {city && (
                  <>
                    {/* The name changes with the city chosen: it settles in, a beat late. */}
                    <span key={city.slug} className="inline-block animate-rise">
                      {city.name}
                    </span>{" "}
                  </>
                )}
                trip
              </h1>
              <p className="text-body text-ink-2">
                An AI picks the places, an optimizer plans the&nbsp;walk.
              </p>
            </header>

            {tripNeedsLogIn && (
              <Notice tone="info" icon="bed">
                This link opens a saved trip, which only its owner can see.{" "}
                <Link
                  href={authHref("/login", `/?trip=${tripId}`)}
                  className="font-bold underline underline-offset-3"
                >
                  Log in
                </Link>{" "}
                to open it.
              </Notice>
            )}

            {formShown ? (
              <>
                {shown && formOpen && status.kind === "idle" && (
                  <div className="-mt-2 flex justify-end">
                    <Button variant="quiet" size="sm" icon="x" onClick={() => setFormOpen(false)}>
                      Keep the current plan
                    </Button>
                  </div>
                )}
                <PlanForm
                  cities={cities}
                  citiesFailed={citiesFailed}
                  onRetryCities={retryCities}
                  city={city}
                  onCityChange={changeCity}
                  cityNote={
                    citySwitch &&
                    city && (
                      <Notice
                        tone="neutral"
                        icon="swap"
                        role="status"
                        title={`Cleared ${clearedPlaces(citySwitch)} in ${citySwitch.from.name}.`}
                        action={
                          <button
                            type="button"
                            onClick={undoCitySwitch}
                            className="inline-flex shrink-0 items-center gap-1 font-bold text-ink underline-offset-3 hover:underline"
                          >
                            <Icon name="undo" size={15} />
                            Undo
                          </button>
                        }
                      />
                    )
                  }
                  conflict={conflict}
                  timeZone={timeZone}
                  text={text}
                  onTextChange={setText}
                  start={start}
                  picking={pickingNow}
                  onTogglePicking={() => setPicking((p) => (p === "start" ? null : "start"))}
                  onClearStart={() => setStart(null)}
                  onToggleRoundTrip={() =>
                    setStart((s) => (s ? { ...s, round_trip: !s.round_trip } : s))
                  }
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
                  dayCount={dayCount}
                  onDayCountChange={setDayCount}
                  eachDay={eachDay}
                  onEachDayChange={setEachDay}
                  dayHours={dayHours}
                  onDayHoursChange={changeDayHours}
                  loading={status.kind === "loading"}
                  onSubmit={submit}
                />
              </>
            ) : (
              <div className="flex items-start gap-3 rounded-panel bg-canvas py-3 pr-3 pl-4">
                <Icon name="sparkle" size={18} className="mt-0.5 text-ink-3" />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-x-2 text-meta font-bold text-ink-2">
                    Your request
                    {shown && (
                      <span className="inline-flex items-center gap-0.5 text-ink">
                        <Icon name="pin" size={13} className="text-ink-3" />
                        {cityName(cities, shown.city)}
                      </span>
                    )}
                  </p>
                  <p className="line-clamp-2 text-small text-ink">“{text}”</p>
                </div>
                <Button size="sm" icon="pencil" onClick={() => setFormOpen(true)}>
                  Change
                </Button>
              </div>
            )}

            {status.kind === "error" && (
              <Notice tone="stop" role="alert">
                {status.message}
              </Notice>
            )}

            {shown === null && <ProofCard className="shadow-none lg:hidden" />}

            {shown && (
              <PlanResult
                plan={shown}
                cityName={cityName(cities, shown.city)}
                trip={trip}
                draft={tripDraft !== null}
                onSaveDraft={saveDraft}
                onDiscardDraft={discardDraft}
                applying={applying}
                onEditDay={trip ? editDay : null}
                editingDay={editingDay}
                onFindVenues={trip ? openVenues : null}
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
        )}
      </main>
    </div>
  );
}
