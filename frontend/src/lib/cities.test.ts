import { describe, expect, it } from "vitest";

import {
  cityBounds,
  cityGroups,
  cityName,
  citiesNamedIn,
  conflictingCity,
  examplesFor,
  findCity,
  pickCity,
  placeSearchHint,
} from "./cities";
import type { City } from "./types";

const LISBON: City = {
  slug: "lisbon",
  name: "Lisbon",
  timezone: "Europe/Lisbon",
  bbox: [-9.2298, 38.6913, -9.0866, 38.7964],
};
const BERLIN: City = {
  slug: "berlin",
  name: "Berlin",
  timezone: "Europe/Berlin",
  bbox: [13.0883, 52.3382, 13.7612, 52.6756],
};
const SAO_PAULO: City = {
  slug: "sao-paulo",
  name: "São Paulo",
  timezone: "America/Sao_Paulo",
  bbox: [-46.83, -23.79, -46.36, -23.36],
};
const CITIES = [LISBON, BERLIN, SAO_PAULO];

describe("citiesNamedIn", () => {
  it("finds the cities a request names, in order, ignoring case and accents", () => {
    expect(citiesNamedIn("3 days in berlin, then LISBON", CITIES)).toEqual([BERLIN, LISBON]);
    expect(citiesNamedIn("A weekend in Sao Paulo", CITIES)).toEqual([SAO_PAULO]);
    expect(citiesNamedIn("Viewpoints and old churches", CITIES)).toEqual([]);
  });

  it("matches whole words only", () => {
    expect(citiesNamedIn("Berliner Dom and a Lisbonesque view", CITIES)).toEqual([]);
    expect(citiesNamedIn("(Berlin)", CITIES)).toEqual([BERLIN]);
  });
});

describe("conflictingCity", () => {
  it("is the city the text names when another one is chosen", () => {
    expect(conflictingCity("2 days in Lisbon", BERLIN, CITIES)).toBe(LISBON);
  });

  it("is null when the text names no city, or names the chosen one", () => {
    expect(conflictingCity("Museums and parks", BERLIN, CITIES)).toBeNull();
    expect(conflictingCity("Berlin, not Lisbon", BERLIN, CITIES)).toBeNull();
    expect(conflictingCity("2 days in Lisbon", null, CITIES)).toBeNull();
  });
});

describe("choosing a city", () => {
  it("takes the first preferred city it knows, else the first city", () => {
    expect(pickCity(CITIES, [null, "tokyo", "berlin", "lisbon"])).toBe(BERLIN);
    expect(pickCity(CITIES, [undefined, "tokyo"])).toBe(LISBON);
    expect(pickCity([], ["berlin"])).toBeNull();
  });

  it("finds a city by slug", () => {
    expect(findCity(CITIES, "berlin")).toBe(BERLIN);
    expect(findCity(CITIES, "tokyo")).toBeNull();
    expect(findCity(null, "berlin")).toBeNull();
    expect(findCity(CITIES, null)).toBeNull();
  });
});

describe("city names and areas", () => {
  it("names a city, or turns an unknown slug into words", () => {
    expect(cityName(CITIES, "sao-paulo")).toBe("São Paulo");
    expect(cityName(null, "new-york")).toBe("New York");
  });

  it("turns a bounding box into Leaflet bounds", () => {
    expect(cityBounds(BERLIN)).toEqual([
      [52.3382, 13.0883],
      [52.6756, 13.7612],
    ]);
  });

  it("groups cities by part of the world, Europe first, each in alphabetical order", () => {
    const at = (slug: string, name: string, timezone: string): City => ({
      ...LISBON,
      slug,
      name,
      timezone,
    });
    const tokyo = at("tokyo", "Tokyo", "Asia/Tokyo");
    const sydney = at("sydney", "Sydney", "Australia/Sydney");
    const utc = at("utc", "Nowhere", "UTC");
    const groups = cityGroups([tokyo, LISBON, SAO_PAULO, utc, sydney, BERLIN]);
    expect(groups).toEqual([
      { label: "Europe", cities: [BERLIN, LISBON] },
      { label: "The Americas", cities: [SAO_PAULO] },
      { label: "Asia", cities: [tokyo] },
      { label: "Oceania", cities: [sydney] },
      { label: "Elsewhere", cities: [utc] },
    ]);
  });
});

describe("examples", () => {
  it("has requests for each known city, and general ones for the others", () => {
    expect(examplesFor(BERLIN)[0]).toContain("Berlin");
    expect(examplesFor(SAO_PAULO)).toHaveLength(3);
    expect(examplesFor(SAO_PAULO)[0]).toBe(
      "2 days in São Paulo, first time here. The main sights and one great museum.",
    );
  });

  it("hints at places to search for in the city", () => {
    expect(placeSearchHint("lisbon")).toBe("Search, e.g. Jerónimos or castelo");
    expect(placeSearchHint("tokyo")).toBe("Search, e.g. Senso-ji or Skytree");
    expect(placeSearchHint("sao-paulo")).toBe("Search by name");
    expect(placeSearchHint(null)).toBe("Search by name");
  });
});
