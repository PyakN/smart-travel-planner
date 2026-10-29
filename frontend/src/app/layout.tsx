import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { Suspense, type ReactNode } from "react";

import { AuthProvider } from "@/components/AuthProvider";
import SiteHeader, { HeaderShell } from "@/components/SiteHeader";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Smart Travel Planner",
  description: "AI-picked places in Lisbon, ordered into the shortest walking route.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} h-full antialiased`}>
      <body className="flex h-full flex-col">
        <AuthProvider>
          {/* The header reads the URL (to come back after logging in): a Suspense boundary. */}
          <Suspense fallback={<HeaderShell />}>
            <SiteHeader />
          </Suspense>
          <div className="min-h-0 flex-1">{children}</div>
        </AuthProvider>
      </body>
    </html>
  );
}
