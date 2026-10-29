"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, logIn, signUp } from "@/lib/api";
import { authHref, safeNext } from "@/lib/navigation";

const INPUT =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20";
const MIN_PASSWORD = 8;

const COPY = {
  login: {
    title: "Log in",
    intro: "Open your saved trips and tick off places as you go.",
    submit: "Log in",
    busy: "Logging in…",
  },
  signup: {
    title: "Create an account",
    intro: "Save trips, then tick off places as you visit them.",
    submit: "Sign up",
    busy: "Creating your account…",
  },
};

/** Log-in or sign-up form; afterwards the visitor goes back to `?next=` (the planner by default). */
export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const next = safeNext(useSearchParams().get("next"));
  const router = useRouter();
  const { user, setUser } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = COPY[mode];

  // Logged in already, or just now: on to where the visitor was going.
  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setUser(
        mode === "signup"
          ? await signUp({ email, password, display_name: name })
          : await logIn({ email, password }),
      );
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <main className="h-full overflow-y-auto px-4 py-10">
      <div className="mx-auto max-w-sm rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900">{copy.title}</h1>
        <p className="mt-1 text-sm text-zinc-500">{copy.intro}</p>

        <form onSubmit={submit} className="mt-5 space-y-4">
          {mode === "signup" && (
            <label className="block space-y-1 text-sm font-medium text-zinc-800">
              <span>Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={50}
                autoComplete="name"
                className={INPUT}
              />
            </label>
          )}
          <label className="block space-y-1 text-sm font-medium text-zinc-800">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={254}
              autoComplete="email"
              className={INPUT}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium text-zinc-800">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "signup" ? MIN_PASSWORD : undefined}
              maxLength={128}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              className={INPUT}
            />
            {mode === "signup" && (
              <span className="block text-xs font-normal text-zinc-500">
                At least {MIN_PASSWORD} characters. Passwords cannot be reset yet, so keep it
                somewhere safe.
              </span>
            )}
          </label>

          {error && (
            <p role="alert" className="rounded-md bg-red-50 p-2 text-sm text-red-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-wait disabled:bg-blue-400"
          >
            {busy ? copy.busy : copy.submit}
          </button>
        </form>

        <p className="mt-5 text-sm text-zinc-600">
          {mode === "login" ? "No account yet? " : "Already have an account? "}
          <Link
            href={authHref(mode === "login" ? "/signup" : "/login", next)}
            className="font-medium text-blue-600 hover:underline"
          >
            {mode === "login" ? "Sign up" : "Log in"}
          </Link>
        </p>
      </div>
    </main>
  );
}
