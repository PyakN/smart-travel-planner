import type { City } from "./types";

/** Lower case and without accents, for matching names: "Lisboa São" -> "lisboa sao". */
function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The supported cities a request text names, in the order it names them. */
export function citiesNamedIn(text: string, cities: City[]): City[] {
  const folded = fold(text);
  return cities
    .map((city) => {
      // Whole words only: "Berliner" is not Berlin.
      const word = new RegExp(
        `(?<![\\p{L}\\p{N}])${escapeRegExp(fold(city.name))}(?![\\p{L}\\p{N}])`,
        "u",
      );
      return { city, at: folded.search(word) };
    })
    .filter(({ at }) => at >= 0)
    .sort((a, b) => a.at - b.at)
    .map(({ city }) => city);
}

/**
 * The city a request text names when it is not the chosen one: the backend refuses that
 * plan, so the form offers to switch first. Null when the text names no city, or names the
 * chosen one.
 */
export function conflictingCity(text: string, chosen: City | null, cities: City[]): City | null {
  if (!chosen) return null;
  const named = citiesNamedIn(text, cities);
  return named.some((c) => c.slug === chosen.slug) ? null : (named[0] ?? null);
}

export function findCity(cities: City[] | null, slug: string | null | undefined): City | null {
  return (slug && cities?.find((c) => c.slug === slug)) || null;
}

/** The first of `preferred` (slugs, best first) that is a supported city, else the first city. */
export function pickCity(cities: City[], preferred: (string | null | undefined)[]): City | null {
  for (const slug of preferred) {
    const city = findCity(cities, slug);
    if (city) return city;
  }
  return cities[0] ?? null;
}

/** A city's name; a slug the list does not know reads as words: "new-york" -> "New York". */
export function cityName(cities: City[] | null, slug: string): string {
  return (
    findCity(cities, slug)?.name ??
    slug
      .split(/[-_]/)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

// Parts of the world, from the first part of a city's IANA time zone.
const REGIONS: [prefix: string, label: string][] = [
  ["Europe/", "Europe"],
  ["America/", "The Americas"],
  ["Asia/", "Asia"],
  ["Africa/", "Africa"],
  ["Australia/", "Oceania"],
  ["Pacific/", "Oceania"],
];

/** The cities by part of the world (Europe first), each part in alphabetical order. */
export function cityGroups(cities: City[]): { label: string; cities: City[] }[] {
  const labels = [...new Set(REGIONS.map(([, label]) => label)), "Elsewhere"];
  const regionOf = (city: City) =>
    REGIONS.find(([prefix]) => city.timezone.startsWith(prefix))?.[1] ?? "Elsewhere";
  return labels
    .map((label) => ({
      label,
      cities: cities
        .filter((city) => regionOf(city) === label)
        .sort((a, b) => a.name.localeCompare(b.name, "en")),
    }))
    .filter((group) => group.cities.length > 0);
}

/** A city's bounding box as Leaflet bounds: [[south, west], [north, east]]. */
export function cityBounds({ bbox }: Pick<City, "bbox">): [[number, number], [number, number]] {
  const [west, south, east, north] = bbox;
  return [
    [south, west],
    [north, east],
  ];
}

// Requests that suit what each city has; other cities get the general ones below.
const EXAMPLES: Record<string, string[]> = {
  lisbon: [
    "2 days in Lisbon, first time here. Viewpoints, the castle, Belém and one great museum.",
    "A slow day with kids: parks, the aquarium and a couple of miradouros.",
    "One intense day of art: museums and galleries, no churches please.",
  ],
  berlin: [
    "2 days in Berlin, first time here. The Reichstag, Museum Island and the Brandenburg Gate.",
    "A slow day with kids: the zoo, a big park and the natural history museum.",
    "One day of history: the Wall, memorials and Cold War sites, no churches please.",
  ],
  barcelona: [
    "2 days in Barcelona, first time here. Gaudí, the Gothic Quarter and a view from Montjuïc.",
    "A slow day with kids: parks, the aquarium and the seafront.",
    "One intense day of art: the Picasso museum, Miró and modern galleries.",
  ],
};

/** Example requests for the city, to start from. */
export function examplesFor(city: Pick<City, "slug" | "name">): string[] {
  return (
    EXAMPLES[city.slug] ?? [
      `2 days in ${city.name}, first time here. The main sights and one great museum.`,
      "A slow day with kids: parks, a viewpoint or two and an easy pace.",
      "One intense day of art: museums and galleries, no churches please.",
    ]
  );
}

// Two well-known places of each city, as the place search finds them (by the name in its
// data, its English name or its name in OSM).
const SEARCH_EXAMPLES: Record<string, string> = {
  lisbon: "Jerónimos or castelo",
  berlin: "Reichstag or Brandenburger Tor",
  barcelona: "Sagrada Família or Park Güell",
  amsterdam: "Rijksmuseum or Anne Frank Huis",
  athens: "Parthenon or Acropolis",
  bangkok: "Grand Palace or Wat Arun",
  brussels: "Atomium or Manneken Pis",
  budapest: "Parliament or Széchenyi",
  "buenos-aires": "Teatro Colón or Recoleta",
  "cape-town": "Kirstenbosch or Castle of Good Hope",
  copenhagen: "Den lille Havfrue or Rosenborg",
  dubai: "Burj Khalifa or Dubai Frame",
  dublin: "Guinness or Dublin Castle",
  edinburgh: "Edinburgh Castle or Holyrood",
  florence: "Uffizi or Ponte Vecchio",
  "hong-kong": "Tian Tan Buddha or The Peak",
  istanbul: "Ayasofya or Topkapı",
  krakow: "Wawel or Rynek Główny",
  kyoto: "Kiyomizu-dera or Kinkaku-ji",
  london: "British Museum or Tower Bridge",
  madrid: "Prado or Palacio Real",
  marrakesh: "Jemaa El-Fna or Majorelle",
  "mexico-city": "Templo Mayor or Chapultepec",
  milan: "Duomo or Castello Sforzesco",
  montreal: "Notre-Dame or Mont-Royal",
  munich: "Frauenkirche or Nymphenburg",
  naples: "Castel Nuovo or Capodimonte",
  "new-york": "Statue of Liberty or Central Park",
  oslo: "Operahuset or Vigeland",
  paris: "Tour Eiffel or Louvre",
  porto: "Livraria Lello or Ribeira",
  prague: "Karlův most or Pražský hrad",
  "rio-de-janeiro": "Cristo Redentor or Pão de Açúcar",
  rome: "Colosseo or Trevi",
  "san-francisco": "Golden Gate or Alcatraz",
  seoul: "Gyeongbokgung or N Seoul Tower",
  seville: "Alcázar or Giralda",
  singapore: "Gardens by the Bay or Merlion",
  stockholm: "Vasamuseet or Gamla stan",
  sydney: "Opera House or Taronga",
  taipei: "Taipei 101 or Lungshan",
  tokyo: "Senso-ji or Skytree",
  valencia: "Llotja or Oceanogràfic",
  venice: "Rialto or Palazzo Ducale",
  vienna: "Schönbrunn or Stephansdom",
  warsaw: "Zamek Królewski or Wilanów",
  "washington-dc": "Lincoln Memorial or Capitol",
};

/** The hint in a place search: "Search, e.g. Jerónimos or castelo". */
export function placeSearchHint(slug: string | null): string {
  const example = slug ? SEARCH_EXAMPLES[slug] : undefined;
  return example ? `Search, e.g. ${example}` : "Search by name";
}

const STORED_CITY = "travel-planner:city";

/** The city chosen on this device last time, if the browser keeps it. */
export function storedCity(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(STORED_CITY);
  } catch {
    return null;
  }
}

export function storeCity(slug: string): void {
  try {
    window.localStorage.setItem(STORED_CITY, slug);
  } catch {
    // Private mode or storage off: the choice lasts for this visit only.
  }
}

/** The browser's own time zone, for clocks until the city is known. */
export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}
