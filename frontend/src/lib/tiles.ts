/**
 * The basemap's tiles. With a Mapbox token (NEXT_PUBLIC_MAPBOX_TOKEN) they come from a
 * Mapbox style; without one, from the public OpenStreetMap server, which is fine for
 * development and light use only (https://operations.osmfoundation.org/policies/tiles/).
 * NEXT_PUBLIC_TILE_URL points the map at any other provider instead.
 *
 * All of them are inlined into the browser code when the app builds. A Mapbox token in the
 * browser is a public (pk.) token: restrict it to the site's URLs in the Mapbox account.
 */

export interface TileSettings {
  tileUrl?: string;
  tileAttribution?: string;
  mapboxToken?: string;
  /** `<username>/<style id>`, Mapbox Streets by default. */
  mapboxStyle?: string;
}

export interface TileSource {
  url: string;
  attribution: string;
  tileSize: number;
  /** Mapbox's 512 px tiles cover what four 256 px tiles do, one zoom level down. */
  zoomOffset: number;
  /** No tiles below this zoom (zoom 0 would ask Mapbox for level -1). */
  minZoom: number;
  /** Mapbox tiles need its logo and an "Improve this map" link on the map. */
  mapbox: boolean;
}

export const MAPBOX_STYLE = "mapbox/streets-v12";

const OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const MAPBOX_ATTRIBUTION =
  '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> ' +
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

/** Build settings left empty (an unset Docker build argument) count as not set. */
function setting(value: string | undefined): string | undefined {
  return value?.trim() || undefined;
}

export function tileSource(settings: TileSettings): TileSource {
  const plain = { tileSize: 256, zoomOffset: 0, minZoom: 0, mapbox: false };
  const url = setting(settings.tileUrl);
  if (url) {
    return { ...plain, url, attribution: setting(settings.tileAttribution) ?? OSM_ATTRIBUTION };
  }
  const token = setting(settings.mapboxToken);
  if (!token) return { ...plain, url: OSM_URL, attribution: OSM_ATTRIBUTION };
  const style = setting(settings.mapboxStyle) ?? MAPBOX_STYLE;
  return {
    // {r} is "@2x" on high-density screens: sharper tiles for the same number of requests.
    url: `https://api.mapbox.com/styles/v1/${style}/tiles/512/{z}/{x}/{y}{r}?access_token=${encodeURIComponent(token)}`,
    attribution: MAPBOX_ATTRIBUTION,
    tileSize: 512,
    zoomOffset: -1,
    minZoom: 1,
    mapbox: true,
  };
}

/** Mapbox's "Improve this map" link, opening its feedback form at the place on the map. */
export function mapboxFeedbackLink(lon: number, lat: number, zoom: number): string {
  const href = `https://apps.mapbox.com/feedback/#/${lon.toFixed(5)}/${lat.toFixed(5)}/${Math.round(zoom)}`;
  return `<strong><a href="${href}" target="_blank" rel="noopener">Improve this map</a></strong>`;
}
