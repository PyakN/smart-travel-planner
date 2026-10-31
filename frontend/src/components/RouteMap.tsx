"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useLayoutEffect, useState } from "react";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { categoryLabel, dayColor, rideName } from "@/lib/format";
import { iconSvg } from "@/lib/icons";
import type { LonLat, PlanResponse, RouteSegment, StartPoint, Venue } from "@/lib/types";
import { openingLabel, venueIcon, venueTypeLabel } from "@/lib/venues";

const LISBON: L.LatLngTuple = [38.7223, -9.1393];
// Other days, muted: DESIGN.md `field`.
const INACTIVE = "#8c959e";
// The white casing under every line, as on a transit diagram.
const CASING = "#ffffff";

// Standard OpenStreetMap tiles: free with attribution, fine for development and light use
// (https://operations.osmfoundation.org/policies/tiles/). Point NEXT_PUBLIC_TILE_URL at a
// provider with an API key for real traffic.
const TILE_URL =
  process.env.NEXT_PUBLIC_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  process.env.NEXT_PUBLIC_TILE_ATTRIBUTION ??
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export interface RouteMapProps {
  plan: PlanResponse | null;
  selectedDay: number;
  onSelectDay: (day: number) => void;
  start: StartPoint | null;
  picking: boolean;
  onPick: (lat: number, lon: number) => void;
  highlightedStop: number | null;
  /** Places to eat and drink found around `search`, shown while searching. */
  venues?: Venue[];
  /** Where the venue search looks, and how far. */
  search?: { lat: number; lon: number; radius_m: number } | null;
  highlightedVenue?: number | null;
  onSelectVenue?: (venueId: number) => void;
}

function toLatLng([lon, lat]: LonLat): L.LatLngTuple {
  return [lat, lon];
}

function stopIcon(label: number, color: string, highlighted: boolean): L.DivIcon {
  const size = highlighted ? 36 : 28;
  return L.divIcon({
    className: "",
    html: `<div class="stop-marker${highlighted ? " is-highlighted" : ""}" style="background:${color};width:${size}px;height:${size}px">${label}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function venueMarker(venue: Venue, highlighted: boolean): L.DivIcon {
  const size = highlighted ? 34 : 26;
  const kind = venue.category === "nightlife" ? "drinks" : "food";
  return L.divIcon({
    className: "",
    html: `<div class="venue-marker venue-marker-${kind}${highlighted ? " is-highlighted" : ""}" style="width:${size}px;height:${size}px">${iconSvg(venueIcon(venue.venue_type), Math.round(size * 0.55), 2)}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// A map pin in ink with a tram-yellow centre: where the venue search looks.
const pinIcon = L.divIcon({
  className: "",
  html: `<svg class="search-pin" viewBox="0 0 32 40" width="32" height="40" aria-hidden="true"><title>Where the search looks</title><path d="M16 38s13-11.6 13-22.5a13 13 0 0 0-26 0C3 26.4 16 38 16 38z" fill="#14202b" stroke="#fff" stroke-width="2"/><circle cx="16" cy="15.5" r="5.5" fill="#ffc629"/></svg>`,
  iconSize: [32, 40],
  iconAnchor: [16, 38],
});

const hotelIcon = L.divIcon({
  className: "",
  html: `<div class="hotel-marker" title="Start point">${iconSvg("bed", 18, 2)}</div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

/** Zooms to the selected day whenever the plan or the day changes. */
function FitToDay({ points, fitKey }: { points: L.LatLngTuple[]; fitKey: string }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [48, 48], maxZoom: 16 });
    }
    // Refit only when the key changes, not on every render's new array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, fitKey]);
  return null;
}

/** Where to get on and off a ride, with the stop names on hover. */
function RideStops({ segment, color }: { segment: RouteSegment; color: string }) {
  const { ride, geometry } = segment;
  if (!ride || geometry.length < 2) return null;
  const ends: [LonLat, string | null][] = [
    [geometry[0], ride.board],
    [geometry[geometry.length - 1], ride.alight],
  ];
  return ends.map(([point, name], i) => (
    <CircleMarker
      key={i}
      center={toLatLng(point)}
      radius={4.5}
      pathOptions={{ color, weight: 2.5, fillColor: "white", fillOpacity: 1 }}
    >
      {name && <Tooltip>{name}</Tooltip>}
    </CircleMarker>
  ));
}

/** Zooms to the search area whenever its point or radius changes. */
function FitToSearch({ lat, lon, radius_m }: { lat: number; lon: number; radius_m: number }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(L.latLng(lat, lon).toBounds(radius_m * 2), { padding: [24, 24] });
  }, [map, lat, lon, radius_m]);
  return null;
}

function PickStart({ enabled, onPick }: { enabled: boolean; onPick: RouteMapProps["onPick"] }) {
  useMapEvents({
    click(event) {
      if (enabled) onPick(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

/**
 * Whether the map is on screen. Next.js keeps a page it navigates away from (React Activity):
 * hidden, with its effects cleaned up, then shown again on the way back. react-leaflet removes
 * its Leaflet map in that cleanup but never makes a new one, and the layers would then draw on
 * the removed map. So the map is unmounted while hidden and made afresh each time it is shown.
 */
function useShown(): boolean {
  const [shown, setShown] = useState(false);
  useLayoutEffect(() => {
    // The effect is the only signal that the page was shown again, so it sets the state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setShown(true);
    return () => setShown(false);
  }, []);
  return shown;
}

export default function RouteMap({
  plan,
  selectedDay,
  onSelectDay,
  start,
  picking,
  onPick,
  highlightedStop,
  venues = [],
  search = null,
  highlightedVenue = null,
  onSelectVenue,
}: RouteMapProps) {
  const shown = useShown();
  const days = plan?.days ?? [];
  const active = days.find((d) => d.day === selectedDay);
  const fitPoints: L.LatLngTuple[] = active
    ? [
        ...active.stops.map((s): L.LatLngTuple => [s.lat, s.lon]),
        ...active.segments.flatMap((seg) => seg.geometry.map(toLatLng)),
      ]
    : [];

  if (!shown) return <div className="h-full w-full bg-canvas" />;
  return (
    <MapContainer
      center={LISBON}
      zoom={13}
      className={`h-full w-full ${picking ? "cursor-crosshair" : ""}`}
      scrollWheelZoom
    >
      <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
      <PickStart enabled={picking} onPick={onPick} />
      {plan && active && !search && (
        <FitToDay points={fitPoints} fitKey={`${plan.id}:${selectedDay}`} />
      )}

      {/* Other days stay visible but muted; click one to switch to it. */}
      {days
        .filter((d) => d.day !== selectedDay)
        .map((d) => (
          <div key={`inactive-${d.day}`}>
            {d.segments.map((seg, i) => (
              <Polyline
                key={i}
                positions={seg.geometry.map(toLatLng)}
                pathOptions={{
                  color: INACTIVE,
                  weight: 3,
                  opacity: 0.6,
                  dashArray: seg.mode === "transit" ? "6 8" : undefined,
                }}
                eventHandlers={{ click: () => onSelectDay(d.day) }}
              />
            ))}
            {d.stops.map((s) => (
              <CircleMarker
                key={s.place_id}
                center={[s.lat, s.lon]}
                radius={5}
                pathOptions={{ color: "white", weight: 1.5, fillColor: INACTIVE, fillOpacity: 1 }}
                eventHandlers={{ click: () => onSelectDay(d.day) }}
              />
            ))}
          </div>
        ))}

      {active && (
        <>
          {active.segments.map((seg, i) => (
            <Polyline
              key={`casing-${i}`}
              positions={seg.geometry.map(toLatLng)}
              interactive={false}
              pathOptions={{
                color: CASING,
                weight: seg.mode === "transit" ? 8 : 9,
                opacity: 0.85,
                lineCap: "round",
                lineJoin: "round",
              }}
            />
          ))}
          {active.segments.map((seg, i) => (
            <Polyline
              key={`active-${i}`}
              positions={seg.geometry.map(toLatLng)}
              pathOptions={{
                color: dayColor(active.day),
                weight: seg.mode === "transit" ? 4 : 5,
                opacity: 1,
                dashArray: seg.mode === "transit" ? "1 9" : undefined,
                lineCap: "round",
                lineJoin: "round",
              }}
            >
              {seg.ride && <Tooltip sticky>{rideName(seg.ride)}</Tooltip>}
            </Polyline>
          ))}
          {active.segments.map((seg, i) => (
            <RideStops key={`ride-stops-${i}`} segment={seg} color={dayColor(active.day)} />
          ))}
          {active.stops.map((s, i) => (
            <Marker
              // While a point is picked, a click on a marker sets it there: markers let
              // clicks through then. Leaflet reads `interactive` once, hence the key.
              key={`${s.place_id}-${picking}`}
              interactive={!picking}
              position={[s.lat, s.lon]}
              icon={stopIcon(i + 1, dayColor(active.day), highlightedStop === s.place_id)}
              zIndexOffset={highlightedStop === s.place_id ? 1000 : 0}
            >
              <Popup>
                <strong>{s.name}</strong>
                <br />
                {categoryLabel(s.category)}, {s.arrive}–{s.leave}
              </Popup>
            </Marker>
          ))}
        </>
      )}

      {start && <Marker position={[start.lat, start.lon]} icon={hotelIcon} />}

      {search && (
        <>
          <FitToSearch {...search} />
          {/* The search area lightens the map under the route, below the lines (pane 400). */}
          <Pane name="search-area" style={{ zIndex: 350 }}>
            <Circle
              center={[search.lat, search.lon]}
              radius={search.radius_m}
              pathOptions={{
                color: "#14202b",
                weight: 1.5,
                opacity: 0.55,
                dashArray: "4 6",
                fillColor: "#ffffff",
                fillOpacity: 0.45,
              }}
              interactive={false}
            />
          </Pane>
          {venues.map((venue) => (
            <Marker
              key={`${venue.id}-${picking}`}
              interactive={!picking}
              position={[venue.lat, venue.lon]}
              icon={venueMarker(venue, highlightedVenue === venue.id)}
              zIndexOffset={highlightedVenue === venue.id ? 1000 : 500}
              eventHandlers={{ click: () => onSelectVenue?.(venue.id) }}
            >
              <Tooltip direction="top" offset={[0, -12]}>
                <strong>{venue.name}</strong>
                <br />
                {venueTypeLabel(venue.venue_type)}, {openingLabel(venue).text}
              </Tooltip>
            </Marker>
          ))}
          <Marker
            position={[search.lat, search.lon]}
            icon={pinIcon}
            zIndexOffset={1500}
            interactive={false}
          />
        </>
      )}
    </MapContainer>
  );
}
