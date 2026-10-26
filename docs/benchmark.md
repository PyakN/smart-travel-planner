# Route benchmark: optimizer vs LLM-only ordering

**Question:** how much walking does the geo-optimizer save compared to letting the LLM order the trip?

Run it yourself (from `backend/`; it makes real LLM and OSRM calls):

```bash
python evals/route_benchmark.py
```

## Method

The five requests from `evals/selection_eval.py` each go through the real selection pipeline (Gemini picks the places), then four routings of the **same places** are compared:

| | Routing | What it represents |
|---|---|---|
| A | Selection order, cut into equal days | A naive LLM planner that lists places in the order it thinks of them |
| B | LLM itinerary | The LLM arranges the days and the order itself. It gets every place's coordinates and is told to minimise back-and-forth: the strongest LLM-only baseline |
| C | Optimizer, haversine × 1.3 | Our planner with straight-line estimates only |
| D | Optimizer, OSRM | Our planner with real walking distances (the default) |

Rules of the comparison:
- **Distances:** every routing is scored on the same OSRM foot matrix (FOSSGIS public server).
- **Start and end:** free start, open end; there is no hotel.
- **Time budget:** visit durations and the pace's daily budget are reported, but nothing is trimmed, so all four routings keep the same stops.
- **OR-Tools reference:** OR-Tools (guided local search, 1 s per day) re-solves each of D's days to measure how far our TSP is from near-optimal.
- **Crossings ("zigzags"):** pairs of route legs that cross each other.

## Results

Run on 2026-10-26, `gemini-3.5-flash-lite`, Lisbon (2,143 OSM places).

| Case | Stops / days, pace | A: selection order | B: LLM itinerary | C: opt. haversine | D: opt. OSRM | D vs A | D vs B | D gap to OR-Tools |
|---|---|---|---|---|---|---|---|---|
| views-and-churches-with-kids | 8 / 2, relaxed | 10.6 km, 0× | 6.1 km, 1× | 5.7 km, 0× | **4.6 km**, 0× | −57% | −24% | +0.0% |
| intense-art-day | 8 / 1, intense | 29.1 km, 9× | 11.9 km, 0× | 11.9 km, 0× | **11.9 km**, 0× | −59% | 0% | +0.0% |
| no-churches | 18 / 3, moderate | 45.4 km, 2× | **15.9 km**, 0× | 16.2 km, 0× | 16.7 km, 0× | −63% | +5% | +0.0% |
| named-places | 12 / 2, moderate | 23.6 km, 1× | 13.8 km, 0× | 20.4 km, 0× | **13.7 km**, 0× | −42% | −1% | −0.0% |
| prompt-injection | 6 / 1, moderate | 33.0 km, 1× | 16.7 km, 0× | 16.7 km, 0× | **16.7 km**, 0× | −49% | 0% | +0.0% |
| **Total** | | 141.7 km, 13× | 64.4 km, 1× | 70.9 km, 0× | **63.6 km, 0×** | **−55%** | **−1%** | |

The optimizer takes ≤ 8 ms per trip. The OSRM matrix request takes 1–9 s on the public server, which is a network cost, not an algorithm cost.

## Findings

1. **Against a naive ordering the optimizer cuts walking by more than half** (−55%, every case −42% to −63%) and removes all 13 crossings.
2. **Against the LLM's own best effort the optimizer is about even (−1% in total), and it is consistent.**
   - It is never worse on single-day trips.
   - It wins clearly when the LLM mis-orders a dense area (−24% in the kids case, where the LLM's route also crossed itself).
   - It loses 5% on one 3-day case.
   - The LLM itinerary costs one more LLM call and has no guarantees: on the first run it produced a 9.5 h day against an 8 h budget.
3. **The per-day TSP is solved: 0.0% gap to OR-Tools on every day.** Every remaining difference comes from how stops are **split into days**.
4. **Real walking distances matter.**
   - Straight-line estimates (C) were 12% worse in total than OSRM (D).
   - They were up to 49% worse on named-places, where routes have to go around the hills and the river front.
   - OSRM puts Praça do Comércio → Castelo at 1,026 m on foot, against 755 m in a straight line.

### The first run, and what changed

The first version split days by **equal stop counts** and lost to the LLM itinerary by 7% in total, and by 15–16% on both multi-day cases. The LLM made unbalanced days (for example 3 and 9 stops) that kept dense neighbourhoods together.

The fix was to balance days by **time** instead:
- **Time-limited split:** a day may take any number of stops that fits the pace's daily budget, but at least half the average.
- **Relocation:** a local search then moves stops between days while that shortens the total walk.

That turned −7% into +1% in the optimizer's favour.

## Guarantees and limits

- **Never longer than the selection order.** One candidate split is the selection order itself, and each day's TSP is seeded with it. Unit tests check this over random trips; it holds whenever that order fits the time budget.
- **Variance.** The LLM picks slightly different places on each run, so the per-case numbers move a few percent between runs. The conclusions above held across runs.
- **No opening hours yet.** Visits are scheduled with fixed per-category durations, but OSM `opening_hours` are not checked.
- **Remaining gap on multi-day trips.** Swap moves between days or a joint optimisation (VRP) would likely close the 5% case. That is future work.
