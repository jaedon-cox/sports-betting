import type { Metadata } from "next";
import { Big_Shoulders_Display, IBM_Plex_Mono, Public_Sans } from "next/font/google";

import { FixtureBanner } from "@/components/chrome/fixture-banner";
import { SiteFooter } from "@/components/chrome/site-footer";
import { isSupabaseConfigured } from "@/lib/supabase/config";

import "./globals.css";

// Self-hosted at build time (§4.3): no external font request, no layout shift.
const display = Big_Shoulders_Display({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});
const body = Public_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Night Ledger — MLB +EV", template: "%s · Night Ledger" },
  description:
    "Closing-line-value tracking for a calibrated MLB pricing model. Every evaluated game, not only the bets.",
};

/**
 * Deliberately reads nothing per-user. The root layout wraps every cacheable
 * page, so a session lookup here would make the whole app dynamic and would
 * bake one reader's identity into any shared render. Signed-in chrome lives in
 * (app)/layout.tsx; the reader's email is shown on /account, which is never
 * cached.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body className="min-h-screen">
        {!isSupabaseConfigured && <FixtureBanner />}
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
