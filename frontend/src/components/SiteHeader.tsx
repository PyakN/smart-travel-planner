"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/AuthProvider";
import { cn } from "@/components/ui/cn";
import { LogoMark } from "@/components/ui/Logo";
import { logOut } from "@/lib/api";
import { authHref } from "@/lib/navigation";

// On the ink band the focus ring turns white so it stays visible.
const ON_INK_FOCUS = "focus-visible:outline-white";
const NAV_LINK = cn(
  "inline-flex h-9 items-center rounded-control px-3 text-sm font-semibold text-white/80 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-60",
  ON_INK_FOCUS,
);

export function HeaderShell({ children }: { children?: ReactNode }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 bg-ink px-4 text-white lg:px-6">
      <Link
        href="/"
        className={cn("-mx-1 flex items-center gap-2.5 rounded-control px-1 py-1", ON_INK_FOCUS)}
      >
        <LogoMark />
        {/* Narrow phones keep the mark; the name stays the link's spoken label. */}
        <span className="font-display text-[19px] leading-none font-semibold tracking-[0.005em] max-[480px]:sr-only">
          Smart Travel Planner
        </span>
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
      <nav aria-label="Account" className="flex items-center gap-1">
        <Link
          href="/trips"
          aria-current={pathname === "/trips" ? "page" : undefined}
          className={cn(NAV_LINK, pathname === "/trips" && "bg-white/10 text-white")}
        >
          My trips
        </Link>
        {user && (
          <>
            <span
              className="hidden max-w-40 truncate px-2 text-sm text-white/60 sm:inline"
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
              className={cn(
                "ml-1 inline-flex h-9 items-center rounded-control bg-white px-3.5 text-sm font-bold text-ink transition-colors hover:bg-white/90",
                ON_INK_FOCUS,
              )}
            >
              Sign up
            </Link>
          </>
        )}
      </nav>
    </HeaderShell>
  );
}
