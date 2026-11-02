"use client";

import type { ReactNode } from "react";

import { buttonClass } from "@/components/ui/Button";
import { Hint } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { gpxUrl } from "@/lib/api";
import { googleMapsRoutes, mapsRouteLabel } from "@/lib/export";
import type { IconName } from "@/lib/icons";
import type { PlannedDay, PlanResponse } from "@/lib/types";

function Section({
  icon,
  title,
  children,
}: {
  icon: IconName;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-sm font-bold text-ink">
        <Icon name={icon} size={16} className="text-ink-3" />
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * Take the plan elsewhere: the selected day as Google Maps directions, the plan or the day as
 * a GPX file for GPS and map apps.
 */
export default function ExportPanel({
  id,
  plan,
  day,
  visited,
}: {
  id: string;
  plan: PlanResponse;
  day: PlannedDay;
  /** Visited stops of a saved trip: Google Maps leads through the others. */
  visited: ReadonlySet<number> | null;
}) {
  const routes = googleMapsRoutes(day, plan.start, visited ?? undefined);
  const underWay = routes.length > 0 && day.stops.some((s) => visited?.has(s.place_id));
  const several = plan.days.length > 1;
  const download = buttonClass({ size: "sm" });
  return (
    <div
      id={id}
      role="region"
      aria-label="Export"
      className="animate-rise space-y-4 rounded-panel border border-line bg-surface p-3.5"
    >
      <Section icon="map" title={`Day ${day.day} in Google Maps`}>
        {routes.length === 0 ? (
          <Hint>Every stop of day {day.day} is visited.</Hint>
        ) : routes.length === 1 ? (
          <a href={routes[0].url} target="_blank" rel="noreferrer" className={download}>
            <Icon name="external" size={16} />
            {underWay ? "Open the rest of the day" : "Open the day's route"}
          </a>
        ) : (
          <ol className="space-y-1.5 text-small">
            {routes.map((route, i) => (
              <li key={route.url}>
                <a
                  href={route.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 font-bold text-ink underline-offset-3 hover:underline"
                >
                  <span className="font-display text-[15px] font-semibold tabular-nums">
                    {i + 1}.
                  </span>
                  {mapsRouteLabel(route)}
                  <Icon name="external" size={14} className="text-ink-3" />
                </a>
              </li>
            ))}
          </ol>
        )}
        {routes.length > 0 && (
          <Hint>
            {underWay
              ? "From where you are, through the stops you have not visited. "
              : "The stops in their order. "}
            {routes.length > 1 &&
              "Google Maps takes one way of travelling per route and at most 11 places, so the day opens in parts."}
          </Hint>
        )}
      </Section>
      <Section icon="download" title="GPX file">
        <div className="flex flex-wrap gap-2">
          {several && (
            <a href={gpxUrl(plan.id)} download className={download}>
              <Icon name="download" size={16} />
              All {plan.days.length} days
            </a>
          )}
          <a href={gpxUrl(plan.id, day.day)} download className={download}>
            <Icon name="download" size={16} />
            {several ? `Day ${day.day}` : "Download"}
          </a>
        </div>
        <Hint>
          For Organic Maps, OsmAnd, Komoot and GPS devices: the stops as waypoints with their times,
          each day as a track.
        </Hint>
      </Section>
    </div>
  );
}
