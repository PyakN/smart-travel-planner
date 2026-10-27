"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { categoryLabel, dayColor, rideName } from "@/lib/format";
import type { LonLat, PlanResponse, RouteSegment, StartPoint } from "@/lib/types";

const LISBON: L.LatLngTuple = [38.7223, -9.1393];
const INACTIVE = "#94a3b8";

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
}

function toLatLng([lon, lat]: LonLat): L.LatLngTuple {
  return [lat, lon];
}

function stopIcon(label: number, color: string, highlighted: boolean): L.DivIcon {
  const size = highlighted ? 36 : 28;
  return L.divIcon({
    className: "",
    html: `<div class="stop-marker" style="background:${color};width:${size}px;height:${size}px">${label}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const hotelIcon = L.divIcon({
  className: "",
  html: '<div class="hotel-marker" title="Start point">H</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
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
      radius={4}
      pathOptions={{ color, weight: 2, fillColor: "white", fillOpacity: 1 }}
    >
      {name && <Tooltip>{name}</Tooltip>}
    </CircleMarker>
  ));
}

function PickStart({ enabled, onPick }: { enabled: boolean; onPick: RouteMapProps["onPick"] }) {
  useMapEvents({
    click(event) {
      if (enabled) onPick(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

export default function RouteMap({
  plan,
  selectedDay,
  onSelectDay,
  start,
  picking,
  onPick,
  highlightedStop,
}: RouteMapProps) {
  const days = plan?.days ?? [];
  const active = days.find((d) => d.day === selectedDay);
  const fitPoints: L.LatLngTuple[] = active
    ? [
        ...active.stops.map((s): L.LatLngTuple => [s.lat, s.lon]),
        ...active.segments.flatMap((seg) => seg.geometry.map(toLatLng)),
      ]
    : [];

  return (
    <MapContainer
      center={LISBON}
      zoom={13}
      className={`h-full w-full ${picking ? "cursor-crosshair" : ""}`}
      scrollWheelZoom
    >
      <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
      <PickStart enabled={picking} onPick={onPick} />
      {plan && active && <FitToDay points={fitPoints} fitKey={`${plan.id}:${selectedDay}`} />}

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
              key={`active-${i}`}
              positions={seg.geometry.map(toLatLng)}
              pathOptions={{
                color: dayColor(active.day),
                weight: seg.mode === "transit" ? 4 : 5,
                opacity: 0.9,
                dashArray: seg.mode === "transit" ? "2 10" : undefined,
                lineCap: "round",
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
              key={s.place_id}
              position={[s.lat, s.lon]}
              icon={stopIcon(i + 1, dayColor(active.day), highlightedStop === s.place_id)}
              zIndexOffset={highlightedStop === s.place_id ? 1000 : 0}
            >
              <Popup>
                <strong>{s.name}</strong>
                <br />
                {categoryLabel(s.category)} · {s.arrive}–{s.leave}
              </Popup>
            </Marker>
          ))}
        </>
      )}

      {start && <Marker position={[start.lat, start.lon]} icon={hotelIcon} />}
    </MapContainer>
  );
}
