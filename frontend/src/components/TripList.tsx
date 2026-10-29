"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, deleteAccount, deleteTrip, listTrips, updateTrip } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { authHref } from "@/lib/navigation";
import type { TripSummary, User } from "@/lib/types";

const LINK = "font-medium text-blue-600 hover:underline";
const QUIET_BUTTON = "rounded-md px-2 py-1 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900";

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function summary(trip: TripSummary): string {
  const city = trip.city.charAt(0).toUpperCase() + trip.city.slice(1);
  const days = `${trip.days} ${trip.days === 1 ? "day" : "days"} in ${city}`;
  return trip.start_date ? `${days} · from ${formatDate(trip.start_date)}` : days;
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
    <li className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      {title === null ? (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Link
              href={`/?trip=${trip.id}`}
              className="font-semibold text-zinc-900 hover:text-blue-700"
            >
              {trip.title}
            </Link>
            <p className="text-sm text-zinc-600">{summary(trip)}</p>
          </div>
          <div className="flex shrink-0 gap-1 text-sm">
            <button
              type="button"
              onClick={() => setTitle(trip.title)}
              disabled={busy}
              className={QUIET_BUTTON}
            >
              Rename
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              className="rounded-md px-2 py-1 text-red-700 hover:bg-red-50"
            >
              Delete
            </button>
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
            className="min-w-0 flex-1 rounded-md border border-zinc-300 px-2 py-1 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-400"
          >
            Save
          </button>
          <button type="button" onClick={() => setTitle(null)} className={QUIET_BUTTON}>
            Cancel
          </button>
        </form>
      )}
      <p className="mt-2 line-clamp-2 text-sm text-zinc-500">“{trip.request_text}”</p>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
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
    <section className="space-y-1 border-t border-zinc-200 pt-6 text-sm text-zinc-600">
      <h2 className="font-medium text-zinc-900">Account</h2>
      <p>
        Logged in as {user.display_name} ({user.email}).
      </p>
      <button type="button" onClick={remove} className="text-red-700 hover:underline">
        Delete my account
      </button>
      {error && (
        <p role="alert" className="text-red-700">
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
      <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
        <div className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">My trips</h1>
          <Link href="/" className={`text-sm ${LINK}`}>
            Plan a new trip
          </Link>
        </div>

        {user === null && (
          <div className="rounded-lg border border-zinc-200 bg-white p-6 text-center text-sm text-zinc-600">
            <p>Log in to see the trips you saved.</p>
            <p className="mt-3 space-x-4">
              <Link href={authHref("/login", "/trips")} className={LINK}>
                Log in
              </Link>
              <Link href={authHref("/signup", "/trips")} className={LINK}>
                Create an account
              </Link>
            </p>
          </div>
        )}

        {error && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}

        {user && trips === null && !error && (
          <div className="h-24 animate-pulse rounded-lg bg-zinc-200" aria-label="Loading trips" />
        )}

        {trips?.length === 0 && (
          <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-600">
            No saved trips yet.{" "}
            <Link href="/" className={LINK}>
              Plan a trip
            </Link>
            , then press “Save to my trips”.
          </p>
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
