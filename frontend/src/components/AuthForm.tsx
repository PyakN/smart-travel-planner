"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { INPUT } from "@/components/ui/Field";
import { LogoMark } from "@/components/ui/Logo";
import { Notice } from "@/components/ui/Notice";
import { ApiError, logIn, signUp } from "@/lib/api";
import { authHref, safeNext } from "@/lib/navigation";

const MIN_PASSWORD = 8;

const COPY = {
  login: {
    title: "Log in",
    intro: "Open your saved trips and tick off places as you\u00a0go.",
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-bold text-ink">{label}</span>
      {children}
    </label>
  );
}

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
    <main className="h-full overflow-y-auto px-4 py-10 sm:py-16">
      <div className="mx-auto max-w-[400px] rounded-panel border border-line bg-surface p-6 sm:p-8">
        <span className="text-ink">
          <LogoMark size={32} />
        </span>
        <h1 className="mt-4 font-display text-title font-semibold text-ink">{copy.title}</h1>
        <p className="mt-1 text-body text-ink-2">{copy.intro}</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          {mode === "signup" && (
            <Field label="Name">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={50}
                autoComplete="name"
                className={INPUT}
              />
            </Field>
          )}
          <Field label="Email">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={254}
              autoComplete="email"
              className={INPUT}
            />
          </Field>
          <Field label="Password">
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
              <span className="block text-small text-ink-2">
                At least {MIN_PASSWORD} characters. Passwords cannot be reset yet, so keep it
                somewhere safe.
              </span>
            )}
          </Field>

          {error && (
            <Notice tone="stop" role="alert">
              {error}
            </Notice>
          )}

          <Button
            type="submit"
            variant="primary"
            size="lg"
            block
            disabled={busy}
            aria-busy={busy}
            className="aria-busy:disabled:cursor-wait aria-busy:disabled:opacity-100"
          >
            {busy ? copy.busy : copy.submit}
          </Button>
        </form>

        <p className="mt-6 border-t border-line pt-5 text-sm text-ink-2">
          {mode === "login" ? "No account yet? " : "Already have an account? "}
          <Link
            href={authHref(mode === "login" ? "/signup" : "/login", next)}
            className="font-bold text-ink underline underline-offset-3"
          >
            {mode === "login" ? "Sign up" : "Log in"}
          </Link>
        </p>
      </div>
    </main>
  );
}
