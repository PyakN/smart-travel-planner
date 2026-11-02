import { describe, expect, it } from "vitest";

import { type MapsRoute, MAX_WAYPOINTS, googleMapsRoutes, mapsRouteLabel } from "./export";
import type { PlannedDay, PlannedStop, StartPoint, TravelMode } from "./types";

function stop(place_id: number, travel_mode: TravelMode | null = "walk"): PlannedStop {
  return { place_id, lat: 38.7 + place_id / 100, lon: -9.1, travel_mode } as PlannedStop;
}

function day(stops: PlannedStop[], return_mode: TravelMode | null = null) {
  return { stops, return_mode } satisfies Pick<PlannedDay, "stops" | "return_mode">;
}

/** The query of a route's URL, decoded. */
function query(route: MapsRoute): Record<string, string> {
  const url = new URL(route.url);
  expect(`${url.origin}${url.pathname}`).toBe("https://www.google.com/maps/dir/");
  return Object.fromEntries(url.searchParams);
}

const HOTEL: StartPoint = { lat: 38.6, lon: -9.2, round_trip: false };

describe("googleMapsRoutes", () => {
  it("walks the day's stops in order", () => {
    const [route, ...more] = googleMapsRoutes(day([stop(1, null), stop(2), stop(3)]), null);
    expect(more).toEqual([]);
    expect(query(route)).toEqual({
      api: "1",
      origin: "38.710000,-9.100000",
      destination: "38.730000,-9.100000",
      waypoints: "38.720000,-9.100000",
      travelmode: "walking",
    });
    expect(route.url).toContain("origin=38.710000%2C-9.100000");
    expect(route.url).toContain("waypoints=38.720000%2C-9.100000&");
    expect(mapsRouteLabel(route)).toBe("Stop 1 to stop 3, on foot");
  });

  it("starts at the start point and returns to it on round trips", () => {
    const routes = googleMapsRoutes(day([stop(1), stop(2)], "walk"), {
      ...HOTEL,
      round_trip: true,
    });
    expect(routes).toHaveLength(1);
    const q = query(routes[0]);
    expect([q.origin, q.destination]).toEqual(["38.600000,-9.200000", "38.600000,-9.200000"]);
    expect(q.waypoints).toBe("38.710000,-9.100000|38.720000,-9.100000");
    expect(mapsRouteLabel(routes[0])).toBe("The start and back, on foot");
  });

  it("opens each ride as a route of its own", () => {
    const routes = googleMapsRoutes(
      day([stop(1), stop(2), stop(3, "transit"), stop(4)], "transit"),
      { ...HOTEL, round_trip: true },
    );
    expect(routes.map(mapsRouteLabel)).toEqual([
      "The start to stop 2, on foot",
      "Stop 2 to stop 3, by public transport",
      "Stop 3 to stop 4, on foot",
      "Stop 4 to the start, by public transport",
    ]);
    const ride = query(routes[1]);
    expect(ride.travelmode).toBe("transit");
    expect(ride.waypoints).toBeUndefined();
  });

  it("opens long walks in parts of about the same length", () => {
    const stops = Array.from({ length: 10 }, (_, i) => stop(i + 1));
    const routes = googleMapsRoutes(day(stops, "walk"), { ...HOTEL, round_trip: true });
    expect(routes.map(mapsRouteLabel)).toEqual([
      "The start to stop 6, on foot",
      "Stop 6 to the start, on foot",
    ]);
    expect(query(routes[0]).waypoints.split("|")).toHaveLength(5);
  });

  it("puts up to the waypoints Google Maps takes in one route", () => {
    const stops = Array.from({ length: MAX_WAYPOINTS + 2 }, (_, i) => stop(i + 1));
    const [route, ...more] = googleMapsRoutes(day(stops), null);
    expect(more).toEqual([]);
    expect(query(route).waypoints.split("|")).toHaveLength(MAX_WAYPOINTS);
  });

  it("goes from where the traveller is through the stops left on a day under way", () => {
    const routes = googleMapsRoutes(
      day([stop(1), stop(2), stop(3), stop(4)], "walk"),
      { ...HOTEL, round_trip: true },
      new Set([1, 3]),
    );
    expect(routes.map(mapsRouteLabel)).toEqual(["Where you are to the start, on foot"]);
    const q = query(routes[0]);
    expect(q.origin).toBeUndefined();
    expect(q.waypoints).toBe("38.720000,-9.100000|38.740000,-9.100000");
  });

  it("leads to a lone stop from where the traveller is", () => {
    const routes = googleMapsRoutes(day([stop(1, null)]), null);
    expect(routes.map(mapsRouteLabel)).toEqual(["Where you are to stop 1, on foot"]);
  });

  it("has nothing left to route once every stop is visited", () => {
    expect(googleMapsRoutes(day([stop(1)]), HOTEL, new Set([1]))).toEqual([]);
  });
});
