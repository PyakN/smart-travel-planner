import type { Metadata, Viewport } from "next";
import { Barlow_Semi_Condensed, Public_Sans } from "next/font/google";
import { Suspense, type ReactNode } from "react";

import { AuthProvider } from "@/components/AuthProvider";
import { CitiesProvider } from "@/components/CitiesProvider";
import SiteHeader, { HeaderShell } from "@/components/SiteHeader";

import "./globals.css";

// Reading text: drawn for legibility in public services, with plain zeros for times.
const publicSans = Public_Sans({
  variable: "--font-public",
  subsets: ["latin", "latin-ext"],
});

// Signage voice: headlines, times and the numbers on stops.
const barlow = Barlow_Semi_Condensed({
  variable: "--font-barlow",
  subsets: ["latin", "latin-ext"],
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Smart Travel Planner",
  description: "AI-picked places in your city, ordered into the shortest walking route.",
};

export const viewport: Viewport = {
  themeColor: "#14202b",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${publicSans.variable} ${barlow.variable} h-full antialiased`}>
      <body className="flex h-full flex-col">
        <AuthProvider>
          <CitiesProvider>
            {/* The header reads the URL (to come back after logging in): a Suspense boundary. */}
            <Suspense fallback={<HeaderShell />}>
              <SiteHeader />
            </Suspense>
            <div className="min-h-0 flex-1">{children}</div>
          </CitiesProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
