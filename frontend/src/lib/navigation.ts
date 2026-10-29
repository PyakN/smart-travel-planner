/**
 * Where to go after logging in: a path on this site, else the planner. `next` comes from the
 * URL, so anything that could leave the site ("//evil.example", "https://…") is ignored.
 */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  return next;
}

/** The log-in (or sign-up) page, coming back to `next` afterwards. */
export function authHref(page: "/login" | "/signup", next: string): string {
  const back = safeNext(next);
  return back === "/" ? page : `${page}?${new URLSearchParams({ next: back })}`;
}
