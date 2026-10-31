"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { useCities } from "@/components/CitiesProvider";
import { Button, buttonClass } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { INPUT } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { LogoMark } from "@/components/ui/Logo";
import { Notice } from "@/components/ui/Notice";
import { ApiError, deleteAccount, deleteTrip, listTrips, updateTrip } from "@/lib/api";
import { cityName } from "@/lib/cities";
import { formatDate } from "@/lib/format";
import { authHref } from "@/lib/navigation";
import type { TripSummary, User } from "@/lib/types";

const LINK = "font-bold text-ink underline underline-offset-3";

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function TripFacts({ trip }: { trip: TripSummary }) {
  const city = cityName(useCities().cities, trip.city);
  return (
    <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-small text-ink-2">
      <span className="inline-flex items-center gap-1.5">
        <Icon name="pin" size={15} className="text-ink-3" />
        {trip.days} {trip.days === 1 ? "day" : "days"} in {city}
      </span>
      {trip.start_date && (
        <span className="inline-flex items-center gap-1.5">
          <Icon name="calendar" size={15} className="text-ink-3" />
          From {formatDate(trip.start_date)}
        </span>
      )}
    </p>
  );
}

function TripCard({
  trip,
  onRenamed,
  onDeleted,
}: {
  trip: TripSummary;
  onRenamed: (title: string) => void;
  onDeleted: () => void;
}) {
  const [title, setTitle] = useState<string | null>(null); // a rename in progress
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (title === null) return;
    setBusy(true);
    setError(null);
    try {
      onRenamed((await updateTrip(trip.id, { title })).title);
      setTitle(null);
    } catch (failure) {
      setError(describe(failure));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete “${trip.title}”? Its share link keeps working.`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteTrip(trip.id);
      onDeleted();
    } catch (failure) {
      setError(describe(failure));
      setBusy(false);
    }
  }

  return (
    <li className="rounded-panel border border-line bg-surface p-4 transition-colors hover:border-line-strong sm:p-5">
      {title === null ? (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Link
              href={`/?trip=${trip.id}`}
              className="font-display text-[20px] leading-tight font-semibold text-ink underline-offset-3 hover:underline"
            >
              {trip.title}
            </Link>
            <TripFacts trip={trip} />
          </div>
          <div className="flex shrink-0 gap-1">
            <Button
              variant="quiet"
              size="sm"
              icon="pencil"
              onClick={() => setTitle(trip.title)}
              disabled={busy}
            >
              Rename
            </Button>
            <Button
              variant="quiet"
              size="sm"
              icon="trash"
              onClick={remove}
              disabled={busy}
              className="enabled:hover:bg-stop-soft enabled:hover:text-stop"
            >
              Delete
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={rename} className="flex flex-wrap items-center gap-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={100}
            autoFocus
            aria-label="Trip title"
            className={cn(INPUT, "min-w-0 flex-1")}
          />
          <Button type="submit" variant="dark" disabled={busy} className="h-11">
            Save
          </Button>
          <Button variant="quiet" onClick={() => setTitle(null)} className="h-11">
            Cancel
          </Button>
        </form>
      )}
      <p className="mt-3 line-clamp-2 border-t border-line pt-3 text-small text-ink-2">
        “{trip.request_text}”
      </p>
      {error && (
        <p role="alert" className="mt-2 text-small font-bold text-stop">
          {error}
        </p>
      )}
    </li>
  );
}

function Account({ user }: { user: User }) {
  const { setUser } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (!window.confirm("Delete your account and all your saved trips? This cannot be undone.")) {
      return;
    }
    try {
      await deleteAccount();
      setUser(null);
      router.push("/");
    } catch (failure) {
      setError(describe(failure));
    }
  }

  return (
    <section className="space-y-2 border-t border-line pt-6 text-sm text-ink-2">
      <h2 className="font-display text-[19px] font-semibold text-ink">Account</h2>
      <p>
        Logged in as <span className="font-bold text-ink">{user.display_name}</span> ({user.email}).
      </p>
      <button
        type="button"
        onClick={remove}
        className="font-bold text-stop underline-offset-3 hover:underline"
      >
        Delete my account
      </button>
      {error && (
        <p role="alert" className="font-bold text-stop">
          {error}
        </p>
      )}
    </section>
  );
}

/** The trips of the logged-in user, the most recently changed first. */
export default function TripList() {
  const { user } = useAuth();
  // Kept with the account they belong to, so another account never sees them.
  const [loaded, setLoaded] = useState<{ userId: number; trips: TripSummary[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const userId = user?.id ?? null;
  const trips = loaded && loaded.userId === userId ? loaded.trips : null;

  // Runs again whenever the page is shown (Next.js keeps it hidden in between), so trips
  // saved meanwhile appear.
  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;
    listTrips()
      .then((list) => {
        if (!cancelled) setLoaded({ userId, trips: list });
      })
      .catch((failure: unknown) => {
        if (!cancelled) setError(describe(failure));
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  function change(update: (trips: TripSummary[]) => TripSummary[]) {
    setLoaded((current) => current && { ...current, trips: update(current.trips) });
  }

  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-6 px-4 py-8 sm:py-12">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[30px] leading-[1.05] font-semibold text-ink sm:text-display">
              My trips
            </h1>
            {trips && trips.length > 0 && (
              <p className="mt-1 text-body text-ink-2">
                {trips.length} saved, the most recently changed first.
              </p>
            )}
          </div>
          <Link href="/" className={buttonClass({ variant: "primary" })}>
            <Icon name="plus" size={17} />
            Plan a new trip
          </Link>
        </div>

        {user === null && (
          <div className="rounded-panel border border-line bg-surface p-8 text-center">
            <span className="inline-flex text-ink">
              <LogoMark size={36} />
            </span>
            <p className="mt-3 text-body text-ink">Log in to see the trips you saved.</p>
            <p className="mt-4 flex justify-center gap-2">
              <Link
                href={authHref("/login", "/trips")}
                className={buttonClass({ variant: "dark" })}
              >
                Log in
              </Link>
              <Link href={authHref("/signup", "/trips")} className={buttonClass()}>
                Create an account
              </Link>
            </p>
          </div>
        )}

        {error && (
          <Notice tone="stop" role="alert">
            {error}
          </Notice>
        )}

        {user && trips === null && !error && (
          <ul className="space-y-3" aria-label="Loading trips">
            {[0, 1].map((i) => (
              <li key={i} className="h-32 animate-pulse rounded-panel bg-canvas" />
            ))}
          </ul>
        )}

        {trips?.length === 0 && (
          <div className="rounded-panel border border-dashed border-line-strong p-8 text-center text-body text-ink-2">
            <p className="font-bold text-ink">No saved trips yet.</p>
            <p className="mt-1">
              <Link href="/" className={LINK}>
                Plan a trip
              </Link>
              , then press “Save to my trips”.
            </p>
          </div>
        )}

        {trips && trips.length > 0 && (
          <ul className="space-y-3">
            {trips.map((trip) => (
              <TripCard
                key={trip.id}
                trip={trip}
                onRenamed={(title) =>
                  change((all) => all.map((t) => (t.id === trip.id ? { ...t, title } : t)))
                }
                onDeleted={() => change((all) => all.filter((t) => t.id !== trip.id))}
              />
            ))}
          </ul>
        )}

        {user && <Account user={user} />}
      </div>
    </main>
  );
}
