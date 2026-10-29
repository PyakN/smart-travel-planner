import type { Metadata } from "next";
import { Suspense } from "react";

import AuthForm from "@/components/AuthForm";

export const metadata: Metadata = { title: "Sign up · Smart Travel Planner" };

export default function SignupPage() {
  // AuthForm reads ?next= with useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense>
      <AuthForm mode="signup" />
    </Suspense>
  );
}
