# Frontend

Next.js 16 (App Router, TypeScript strict, Tailwind) with a Leaflet map. Talks to the FastAPI backend through a same-origin proxy: `/api/*` → `BACKEND_URL` (see `next.config.ts`).

## Run

Start the backend first (see the root README), then:

```bash
npm ci
npm run dev          # http://localhost:3000
```

Optional settings: copy `.env.example` to `.env.local`. The map draws Mapbox tiles when `NEXT_PUBLIC_MAPBOX_TOKEN` holds a public Mapbox token (restrict it to the site's URLs in the Mapbox account), else the public OpenStreetMap tiles, which are for development and light use only. Tile settings are inlined into the browser code, so a change needs a restart of `npm run dev` or a new build.

## Checks

```bash
npm run lint         # eslint (next + typescript rules, prettier-compatible)
npm run format       # prettier --write   (format:check in CI and pre-commit)
npm run typecheck    # tsc --noEmit
npm test             # vitest: API client, formatters (opening hours, edit summaries), log-in links
npm run build        # production build
npm run test:e2e     # Playwright end-to-end tests (see below)
```

## End-to-end tests

`e2e/*.spec.ts` drive the real app in Chromium, at desktop (1440 px) and phone (Pixel 7) sizes: plan a trip, switch days and reopen its share link; a plan made without the AI; the warning for a request that names another city; replace a stop and undo it; sign up, save a plan, tick a stop visited and reopen it from My trips; move a saved day's stops by dragging and with the keyboard, then save the order; log in before saving.

`npm run test:e2e` starts both servers itself (`playwright.config.ts`):

- **API** on port 8100: `backend/tests/e2e/server.py` creates (or empties) the database `<name>_e2e` next to `DATABASE_URL`'s, migrates it, seeds 14 Lisbon sights and serves the real app with a scripted LLM (`backend/tests/e2e/llm.py`: it reads requests by the rules plans fall back on and picks the first candidates; a request with `llm-outage` in it fails, as in an outage), straight-line distances, estimated rides, no weather and no rate limits. It uses `backend/.venv`'s Python when there is one, else `python` (`E2E_PYTHON` overrides it).
- **Frontend** on port 3100: a production build in `.next-e2e/`, whose `/api` proxy points at that API, so your dev server and its build are left alone.

Pages never reach the internet (map tiles and photos are blocked). Needs the database running (`docker compose up -d`) and Chromium once: `npx playwright install chromium`. On a failure, `npx playwright show-trace test-results/<test>/trace.zip` replays it.

## Layout

| Path                                 | What                                                                                                                   |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `src/components/Planner.tsx`         | Page state: request, plan, selected day, `?plan=<id>` share links, `?trip=<id>` saved trips                            |
| `src/components/PlanForm.tsx`        | Request text, examples, optional start point (click the map), must-visit places, travel modes, first day and weather   |
| `src/components/MustVisitPicker.tsx` | Place search (`GET /places?q=`) with keyboard navigation; picked places as chips                                       |
| `src/components/PlanResult.tsx`      | Summary, day tabs, the day as a line diagram (times, line, stops, legs); Save to my trips; tick stops to replace, Undo |
| `src/components/StopCard.tsx`        | One stop: time slot, forecast, Wikimedia photo or category icon, AI note, description, hours, links, Visited tick      |
| `src/components/ProofCard.tsx`       | Empty planner: the same places in the AI's order and the optimized order, with the benchmark result                    |
| `src/components/ui/`                 | Atomic pieces of the design system (`DESIGN.md`): Button, fields, toggles, Tag, Notice, Roundel, Icon, Logo            |
| `src/components/DayWeather.tsx`      | A day's weather header: condition, temperatures, chance of rain, daylight and 3-hourly slots (OpenWeatherMap)          |
| `src/components/RouteMap.tsx`        | Leaflet map, client-only. The selected day is drawn in colour (walking solid, tram/metro dotted); other days are muted |
| `src/components/AuthProvider.tsx`    | Who is logged in (`GET /auth/me`; the session cookie is HttpOnly)                                                      |
| `src/components/CitiesProvider.tsx`  | The supported cities (`GET /cities`), read once for every page                                                         |
| `src/components/CityPicker.tsx`      | The trip's city, each with its local time; a select past six cities                                                    |
| `src/components/SiteHeader.tsx`      | Header on every page: My trips, log in / sign up, or the user's name and Log out                                       |
| `src/components/AuthForm.tsx`        | Log-in and sign-up form (`/login`, `/signup`); back to `?next=` afterwards                                             |
| `src/components/TripList.tsx`        | My trips (`/trips`): open, rename, delete; delete the account                                                          |
| `src/proxy.ts`                       | Adds `ORIGIN_SECRET` to the `/api` requests, so a deployed API answers only the website                                |
| `src/lib/api.ts`                     | Typed client for plans, places, `/auth` and `/trips`, with readable errors                                             |
| `src/lib/types.ts`                   | Mirrors `backend/app/schemas/` (plan, place, account, saved_trip)                                                      |
| `src/lib/navigation.ts`              | Same-site `?next=` links for logging in                                                                                |
| `src/lib/icons.ts`                   | The authored SVG icon set, for React (`<Icon>`) and for Leaflet markers                                                |
| `src/lib/cities.ts`                  | Choosing the city, cities a request names, per-city examples and search hints, the last city chosen                    |
| `src/lib/tiles.ts`                   | Map tiles: Mapbox with a token (its logo and feedback link on the map), else OpenStreetMap                             |

`AGENTS.md` is generated by Next.js for coding agents: this Next.js version differs from older ones, and its docs ship in `node_modules/next/dist/docs/`.
