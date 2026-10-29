"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/AuthProvider";
import { logOut } from "@/lib/api";
import { authHref } from "@/lib/navigation";

const NAV_LINK = "rounded-md px-2 py-1 text-zinc-700 hover:bg-zinc-100 hover:text-zinc-900";

export function HeaderShell({ children }: { children?: ReactNode }) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-zinc-200 bg-white px-4 lg:px-6">
      <Link href="/" className="text-sm font-semibold tracking-tight text-zinc-900">
        Smart Travel Planner
      </Link>
      {children}
    </header>
  );
}

export default function SiteHeader() {
  const { user, setUser } = useAuth();
  const pathname = usePathname();
  const query = useSearchParams().toString();
  const here = query ? `${pathname}?${query}` : pathname;
  const onAuthPage = pathname === "/login" || pathname === "/signup";
  const [leaving, setLeaving] = useState(false);

  async function leave() {
    setLeaving(true);
    try {
      await logOut();
      setUser(null);
    } catch {
      // The backend is unreachable, so the session lives on: stay logged in.
    } finally {
      setLeaving(false);
    }
  }

  return (
    <HeaderShell>
      <nav aria-label="Account" className="flex items-center gap-1 text-sm">
        <Link href="/trips" className={NAV_LINK}>
          My trips
        </Link>
        {user && (
          <>
            <span
              className="hidden max-w-40 truncate px-2 text-zinc-500 sm:inline"
              title={user.email}
            >
              {user.display_name}
            </span>
            <button type="button" onClick={leave} disabled={leaving} className={NAV_LINK}>
              Log out
            </button>
          </>
        )}
        {user === null && !onAuthPage && (
          <>
            <Link href={authHref("/login", here)} className={NAV_LINK}>
              Log in
            </Link>
            <Link
              href={authHref("/signup", here)}
              className="rounded-md bg-blue-600 px-3 py-1 font-medium text-white hover:bg-blue-700"
            >
              Sign up
            </Link>
          </>
        )}
      </nav>
    </HeaderShell>
  );
}
