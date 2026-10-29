import type { Metadata } from "next";
import { Suspense } from "react";

import AuthForm from "@/components/AuthForm";

export const metadata: Metadata = { title: "Log in · Smart Travel Planner" };

export default function LoginPage() {
  // AuthForm reads ?next= with useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense>
      <AuthForm mode="login" />
    </Suspense>
  );
}
