# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: city travellers.** Someone spending one to seven days in a city (Lisbon, Berlin or Barcelona) who wants a sightseeing plan they would actually follow, without stitching one together from guides and a map. Both of these moments matter equally:

- **Planning ahead, at a desk.** They describe the trip in their own words ("2 days in Lisbon with kids, we love viewpoints and old churches"). They set a hotel, must-visit places, how they get around, dates and daily hours, then read the plan against the map.
- **Running the day, on a phone.** They are outdoors between sights. They tick stops visited, find somewhere to eat near where they stand, make it the next stop, and approve or discard the re-planned rest of the day.

**Secondary: reviewers.** Engineers, hiring managers and recruiters judging the project. The traveller product comes first. The engineering has to stay legible to reviewers without turning the product into a demo.

## Product Purpose

Turns a free-text trip request into a day-by-day plan of real places. The route is the shortest one that fits each place's opening hours, daylight, the traveller's own hours and, if they ask for it, the weather. The plan then stays accurate while the trip happens.

Success: the traveller gets a plan they would follow, and can change it on the go without it falling apart.

## Positioning

Two layers, strictly separated. The LLM only interprets the request and picks place ids from a candidate list drawn from the database. Coordinates, visiting order and timing always come from the data and the optimizer.

So the product never invents a place, and its route quality is measured: 55% less walking than the LLM's selection order, on par with an itinerary the LLM arranged itself (−1%), and zero route crossings (`docs/benchmark.md`). An LLM-only planner cannot truthfully claim either.

## Operating Context

- **Request:** free text plus optional settings: a start point (hotel) picked on the map, round trip or open end, must-visit places from a name search, walking and/or public transit, first day, number of days, daily start and end (overnight allowed; different hours for each day), and a weather-aware toggle.
- **Plan:** dated days with their hours. Each day has ordered, timed stops with the leg to each one (walking, or transit with its lines and stops). Stop cards carry a Wikimedia photo with credit, a description, the LLM's one-sentence note on why the place suits the traveller, opening hours, forecast and any free time. Days can end in a free evening. Warnings and swaps are explained.
- **Sharing and accounts:** anyone with a plan's link can read it (`?plan=<id>`). An account adds private saved trips (`?trip=<id>`): rename, delete, visited ticks, versions and undo.
- **Changing a saved trip:** "Edit day" removes stops and adds places. "Replace stops" asks the AI for alternatives. Both produce a draft. Dropped stops are listed with a reason, and nothing changes until the traveller saves. Visited stops stay first and never move.
- **Places to eat and drink:** plans never suggest them. The traveller finds them through the venue search near their location, a map pin or the day's last visited stop. "Add to route" picks how long to stay and plans that venue in.
- **Timing:** a new plan takes a few seconds (LLM ~2 s, ~3–9 s in total), with stepwise progress messages. A day edit takes about a second (no LLM).

## Capabilities and Constraints

- **Cities:** the backend plans Lisbon, Berlin and Barcelona. The frontend still assumes Lisbon (map, clock, place search); a city picker is planned.
- **Sights only:** generated plans and AI replacements never include restaurants, cafés, bars, clubs or fado houses. Those come in only as must-visit places or from the venue search.
- **Data sources:** places, opening hours, cuisines, diets and outdoor seating come from OpenStreetMap. Photos (with author and licence) and descriptions come from Wikimedia Commons, Wikipedia and Wikidata. Coverage is partial: in Lisbon, 634 of ~7.2k places have a photo and 440 a description.
- **No ratings or prices:** OSM has none, so the UI shows none until an optional provider (e.g. Foursquare) is added. Google Places is ruled out because its terms forbid showing its content on a non-Google map.
- **Credits:** map data and photo credits must stay visible.
- **Map:** Leaflet with OpenStreetMap tiles from the public tile server. A tile provider with an API key is planned for deployment, and Mapbox GL is optional later.
- **Weather:** OpenWeatherMap 5-day forecast, used only when the traveller turns it on. Days beyond the forecast have no weather.
- **Transit:** real HERE timetables when a key is set. Otherwise rides are estimated, and the plan says which.
- **Errors:** backend messages are shown to the traveller as they are.
- **Terms used across product and API:** plan, trip (a saved plan), day, stop, start point (hotel), round trip, must-visit, pace (relaxed, moderate, intense), visited, edit day, replace stops, draft, save changes, discard, undo, free time, free evening, places to eat and drink, venue.
- **Status:** not deployed yet; there is no demo link.
- **Undecided:**
  - The product name: "Smart Travel Planner" is a working title.
  - The copy voice. Today's copy is plain and literal ("Off: the plan ignores the weather, and no forecast is fetched."). That is the incumbent voice, not a commitment.
  - Export (GPX, Google Maps link), drag-and-drop stops, and ratings and prices.

## Evidence on Hand

- **Route benchmark:** `docs/benchmark.md`. Five request types in Lisbon (2026-10-26, `gemini-3.5-flash-lite`). The optimizer walks 63.6 km in total, against 141.7 km in the selection order and 64.4 km for the LLM's own itinerary, with 0 crossings against 13 and 1. Its TSP is within 0.0% of OR-Tools.
- **Live checks:** the "Result" lines in `PROJECT_PLAN.md`, with timings and the bugs the live runs found.
- **Real data:** Lisbon ~7.2k places (5k to eat and drink), Berlin ~19.7k, Barcelona ~11.3k, all from OSM.
- **Absent:** there are no users, testimonials, usage numbers, ratings, press or live deployment. Do not invent any of them.

## Product Principles

1. **Real places, honest routes.** Everything a traveller sees about a place comes from the data or the algorithm. The LLM's own words stay in its note on why a place suits them.
2. **Explain every change.** When the planner drops, swaps, waits or warns, it says what happened and why, in the traveller's terms: "The day would end at 23:10 instead of 21:30."
3. **Nothing changes a saved trip without consent.** Edits are drafts until saved, dropped stops ask first, undo is always there, and visited stops never move.
4. **Two moments, one plan.** Planning at a desk and running the day on a phone are equally first-class. Neither is the reduced version of the other.
5. **Show the engineering through the product.** Less walking, no zigzags and real opening hours reach reviewers as traveller benefits, not as a separate demo layer.
