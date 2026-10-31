---
name: Smart Travel Planner
description: City days drawn as a transit line. Real places, the shortest walk, set in timetable rhythm.
colors:
  ink: "#14202B"
  ink-2: "#4A5763"
  ink-3: "#66717C"
  field: "#8C959E"
  line: "#E2E5E7"
  line-strong: "#C9CFD4"
  canvas: "#F3F4F2"
  surface: "#FFFFFF"
  signal: "#FFC629"
  signal-hover: "#F5B70A"
  signal-soft: "#FFF3C4"
  signal-ink: "#6B4E00"
  go: "#0E7A50"
  go-soft: "#E2F3EA"
  stop: "#C42B2B"
  stop-soft: "#FCEBEA"
  caution: "#8A5300"
  caution-soft: "#FDEBD3"
  info: "#1D5BBF"
  info-soft: "#E8EFFC"
  evening: "#5B3CC4"
  evening-soft: "#EEEAFB"
  day-1: "#1F5EDB"
  day-2: "#D52F6E"
  day-3: "#12805C"
  day-4: "#C2410C"
  day-5: "#6D3FD1"
  day-6: "#0B7285"
  day-7: "#8A6100"
typography:
  display:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "0em"
  numeral:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.01em"
  heading:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0em"
  body:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  small:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0em"
  meta:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.005em"
rounded:
  xs: "4px"
  sm: "8px"
  md: "12px"
  full: "9999px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
  8: "32px"
  10: "40px"
components:
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.signal-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
    height: "40px"
  button-dark:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
    height: "44px"
  tag:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.xs}"
    padding: "2px 6px"
  roundel:
    backgroundColor: "{colors.day-1}"
    textColor: "{colors.surface}"
    rounded: "{rounded.full}"
    size: "28px"
  header:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    height: "56px"
---

# Design System: Smart Travel Planner

## Overview

**Wayfinding.** The product turns a sentence into a day you can walk. The visual world comes from what every traveller in Lisbon, Berlin and Barcelona already reads without thinking: transit line diagrams, station roundels, departure timetables and city wayfinding signs. These are graphic systems built to be read at a glance, outdoors, in a hurry. That is exactly how the app is used on a phone between sights.

The world lends four things and only four: type, palette, density and one signature move. Layout, navigation and controls stay standard web controls. It should read as a working planner first and as a transit map second.

- **Signature move: the line diagram itinerary.** A planned day is drawn as a transit line. Times sit in a timetable column, a continuous rail runs in the day's line colour (solid for walking, dotted for a ride), and each stop is a numbered station roundel. The map draws the same day in the same colour, with the same roundels and the same solid and dotted legs, so list and map read as one object.
- **The proof moment:** the empty planner shows the mechanism, not a slogan. The same seven places are connected in the order an AI lists them, then redrawn as the optimizer's route, with the measured result beside it (`docs/benchmark.md`: 55% less walking, 13 crossings to 0).
- **Scene:** a traveller in daylight on a phone, or at a desk planning ahead. Both are light, so the ground is light and contrast is high. Dark appears only as the ink header band, the way a station sign carries its name.

Design references from UI/UX Pro Max: *Minimalism & Swiss Style* (its pick for travel and airline tools: grid, high contrast, single accent, no ornament) and its travel palette logic of map colour plus one warm signal. Rejected from its first pass: *Aurora UI* gradients, a scroll-storytelling marketing pattern, and a children's type pairing (Baloo 2, Comic Neue). None of these fit a map tool used outdoors.

## Colors

The strategy is **restrained ground, committed signals**. Neutrals are tinted toward map paper. One warm signal, tram yellow (the trams of Lisbon, the U-Bahn of Berlin), marks the action that moves the trip forward. Seven line colours give each day its identity, and state colours appear only where they carry meaning.

### Primary
- **Tram yellow** `signal #FFC629`: the one primary action per view (Plan my trip, Save to my trips, Save changes, log-in and sign-up submits), the logo mark, the active-day underline on narrow screens and the search pin. Always with ink text (10.5:1). Hover `signal-hover #F5B70A`. `signal-soft #FFF3C4` with `signal-ink #6B4E00` is for selected-for-replacement highlights.

### Neutral
- **Ink** `#14202B`: text, the header band, dark buttons and focus rings. **Ink 2** `#4A5763` is secondary text (7.4:1). **Ink 3** `#66717C` is meta text, at 5.0:1 on white and 4.5:1 on canvas.
- **Field** `#8C959E`: input and checkbox borders (3:1 non-text contrast).
- **Line** `#E2E5E7` for hairline dividers and card borders, **line-strong** `#C9CFD4` for hovered borders and dashed rules.
- **Canvas** `#F3F4F2` (map paper) is the app ground and subtle fills. **Surface** `#FFFFFF` is for panels, cards and inputs.

### Line colours (days)
`day-1 #1F5EDB` blue, `day-2 #D52F6E` magenta, `day-3 #12805C` green, `day-4 #C2410C` orange, `day-5 #6D3FD1` violet, `day-6 #0B7285` teal, `day-7 #8A6100` ochre. Each carries white numerals at 4.7:1 or more. Day 8 repeats day 1. They appear on route lines, roundels, the day tab's roundel and travel-leg rails. They never appear as large background fills.

### States
- `go #0E7A50` / `go-soft #E2F3EA`: visited, open now, saved.
- `stop #C42B2B` / `stop-soft #FCEBEA`: closed, errors, destructive actions.
- `caution #8A5300` / `caution-soft #FDEBD3`: drafts, warnings, dropped stops.
- `info #1D5BBF` / `info-soft #E8EFFC`: weather notes.
- `evening #5B3CC4` / `evening-soft #EEEAFB`: evening places and free evenings.

### Named Rules
- **One yellow per view.** If two things are yellow, one of them is wrong.
- **Line colours mean days.** Never use a day colour for a state, a link or decoration.
- **The map is paper.** Basemap tiles are desaturated so the only saturated ink on the map is the trip itself.

## Typography

Two families, clearly distinct. **Barlow Semi Condensed** carries the signage voice: headlines, trip titles, times, roundel numerals and stats. It descends from road and transit lettering, and its narrow, even figures set timetables cleanly. **Public Sans** carries everything people read in sentences. It was drawn for the U.S. Web Design System to stay legible in public services, it shares Barlow's grotesque lineage, and its zeros are plain. Atkinson Hyperlegible Next was tried first and dropped: its slashed zero made every date and time read like code.

### Hierarchy
- **Display** Barlow Semi Condensed 600, 32px (26px mobile), line height 1.05: the planner's question.
- **Title** Barlow Semi Condensed 600, 24px (21px mobile): trip title, page titles.
- **Numeral** Barlow Semi Condensed 600, 15px, `tabular-nums`: arrive and leave times, roundels, stats.
- **Heading** Public Sans 700, 16px: stop and venue names, section headings.
- **Body** Public Sans 400, 15px, line height 1.5: descriptions, rationale, AI notes. Measure at most 65ch.
- **Small** Public Sans 400, 13px: hints, legs, meta lines.
- **Meta** Public Sans 400, 12px: credits and attribution. Nothing is smaller than 12px.
- **Form labels** Public Sans 700, 14px, sentence case.

### Named Rules
- **No eyebrows, no all-caps labels.** A heading carries its own weight.
- **Times are numerals.** Every clock time and duration is set in the numeral style, tabular.
- **Inputs are 16px on phones** so iOS never zooms the page.

## Layout

- **Shell:** an ink header band (56px) over a two-pane workspace. On desktop (1024px and up) a 480px sidebar (the page's `main`) sits on the left, with the full-bleed map to its right. Below 1024px the map sits on top (38dvh) and the sidebar scrolls below it. Below 480px the header keeps the mark and drops the wordmark, which stays the link's spoken name.
- **Planner states:** with no plan, the sidebar leads with the display question, the request field, examples and trip settings, and the map shows the proof card. With a plan, the request folds into a one-line summary with "Change request", and the plan takes the sidebar.
- **Itinerary grid:** a 44px time column, a 28px rail, then the stop content. The rail is continuous from first to last stop. Below 640px the time column goes and the times lead each card, so stop names keep their width.
- **Spacing:** a 4px base (4, 8, 12, 16, 20, 24, 32, 40). Groups are tight (8–12px). Sections are separated by 24–32px, with more space above a heading than below it.
- **Alignment:** left-aligned throughout. Numerals align on a column.

## Elevation & Depth

Flat by default. Hairline borders do the separating, and only floating layers cast shadows.

### Shadow Vocabulary
- `float`: `0 12px 32px -12px rgb(20 32 43 / 0.28), 0 2px 6px rgb(20 32 43 / 0.08)`, for map overlay cards, popovers, autocomplete lists and dialogs.
- `bar`: `0 -8px 24px -12px rgb(20 32 43 / 0.18)`, for the sticky action bars at the bottom of the sidebar.
- Map markers: `0 1px 3px rgb(20 32 43 / 0.35)`.

### Named Rules
- **Cards don't float.** In-flow cards have a border, never a shadow.

## Shapes

- **Roundels** are full circles: station markers, day badges, the hotel.
- **Controls** (buttons, inputs, selects) use a radius of 8px.
- **Panels and cards** use a radius of 12px.
- **Tags and ride badges** use a radius of 4px, like small enamel sign plates.
- **Toggle chips** (examples, venue kinds, travel modes) are pills, because they are pressed like buttons and read as options.
- Icons are authored SVG on a 24px grid with a 1.75px round-cap stroke. They are never emoji or Unicode glyphs.

## Components

### Buttons
- **Primary** (tram yellow, ink text, 44px tall, 700 weight): one per view. Disabled, it turns `line` grey with Ink 3 text, so it never reads as a faded yellow. Busy, it stays yellow and shows its progress.
- **Dark** (ink, white text): the strong secondary, used for Sign up in the header and the selected state of segmented options.
- **Secondary** (white, line-strong border, ink text): Copy share link, Edit day, Show more.
- **Quiet** (text only, canvas hover): Cancel, Discard, Clear.
- **Danger** (stop red, white text): Drop and save, Delete.
- Press feedback: scale to 0.98 over 150ms. Other disabled buttons sit at 45% opacity with a not-allowed cursor. Loading buttons keep their width and show their progress label: Plan my trip draws its four steps as stops on a line.

### Chips
Example requests, travel modes and venue kinds are pill toggles with `aria-pressed`. Off: white with a line-strong border. On: ink with white text.

### Cards / Containers
Stop cards and venue cards are white with a 1px `line` border, a 12px radius and no shadow. Their states are borders and fills, never shadows:
- **Hover:** `line-strong`.
- **Selected for replacement:** `signal-soft` fill and an ink border.
- **Visited:** a `go` check roundel, with the rail before it drawn in the line colour at full strength.
- **Removed in an edit:** dashed border at 55% opacity, with the name struck through.

### Inputs / Fields
44px tall, white, 1px `field` border, 8px radius, 16px text on phones and 15px on desktop. Focus is a 2px ink outline with a 2px offset, the same ring every focusable element uses. Labels sit above their fields. Hints sit below in 13px Ink 2. Errors sit below in stop red, named with the fix.

### Map
- **Paper:** OpenStreetMap tiles in greyscale (a CSS filter on the tile pane), so the provider and its attribution stay unchanged.
- **Routes:** the selected day in its line colour over a white casing, solid on foot and dotted on a ride. Other days are `field` grey, and clicking one selects it.
- **Markers:** stop roundels (a yellow ring when the stop is hovered in the list), the hotel as an ink square with a bed, places to eat as ink roundels, drinks as evening violet, and the search point as an ink pin with a yellow centre.
- **Search area:** a dashed ink circle with a 45% white fill that lightens the map under it, drawn below the route so the route stays saturated.

### Navigation
The header is an ink band: the logo (a yellow three-stop line mark and the wordmark) on the left, with My trips, the user's name and Log out, or Log in and Sign up on the right. Day tabs are a horizontal tablist. Each tab is a day roundel plus "Day n", the date, and stops and duration. The active tab is white with an ink border, and the rest are quiet.

### Line diagram itinerary (signature)
The day as a transit line, as set out in the Overview. Each row has, in order:
- the time column: arrive in numeral 600 ink, leave in numeral 400 Ink 3;
- the rail: a 3px line in the day colour, dotted where the leg is a ride;
- the roundel: 28px, the day colour, white numeral, with a 2px white ring;
- the stop card.

Travel legs sit on the rail between stops ("Walk 12 min · 900 m", ride badges in the line's own colour). Free time, departures and the free evening are rail annotations with their own icons, not cards. Each time a day or a plan version comes on screen, the list is revealed from the top down (520ms, ease-out-expo), so the line reads as drawing itself. Under reduced motion it renders complete. Visited stops turn their roundel `go` green with a check.

### Motion
One authored moment per surface: the proof card's two routes on the empty planner, and the itinerary's top-down reveal when a plan arrives. Action bars and dialogs rise 6px as they appear (260ms). Under reduced motion, entrances and reveals land at once, while colour changes and the switch thumb still show state.

### Proof card (empty planner)
A floating panel on the map (desktop) or below the form (mobile). An SVG of seven roundels shows the AI's own order as a grey zigzag, then the optimizer's route drawn over it in day-1 blue, with the benchmark result as one sentence. It plays once when it enters the viewport, and is static under reduced motion.

## Do's and Don'ts

### Do:
- **Do** keep one tram-yellow action per view.
- **Do** draw every planned day with the same grammar on the list and on the map: line colour, roundels, solid walking and dotted rides.
- **Do** set every time and duration in tabular numerals.
- **Do** say what changed and why in the product's own words, and keep the backend's messages as they are.
- **Do** keep photo, map and transit credits visible, at 12px.

### Don't:
- **Don't** use emoji or Unicode glyphs as icons.
- **Don't** use eyebrows, all-caps labels, gradient text or glass decoration.
- **Don't** put shadows on in-flow cards, and don't nest cards.
- **Don't** use day colours for anything but days.
- **Don't** show ratings, prices or any number the data does not have.
- **Don't** set any text below 12px or any phone input below 16px.
