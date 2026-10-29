import type { Metadata } from "next";

import TripList from "@/components/TripList";

export const metadata: Metadata = { title: "My trips · Smart Travel Planner" };

export default function TripsPage() {
  return <TripList />;
}
