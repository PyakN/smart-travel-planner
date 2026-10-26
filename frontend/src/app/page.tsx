import { Suspense } from "react";

import Planner from "@/components/Planner";

export default function Home() {
  // Planner reads ?plan= with useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense fallback={<div className="h-dvh animate-pulse bg-zinc-100" />}>
      <Planner />
    </Suspense>
  );
}
