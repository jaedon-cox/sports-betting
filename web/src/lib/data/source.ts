import type { PostgrestError } from "@supabase/supabase-js";

/**
 * Where a given read came from. Surfaced in the UI (components/chrome/
 * demo-banner) so a fixture number is never mistaken for a real one.
 */
export type DataSource = "live" | "fixture";

export interface Sourced<T> {
  data: T;
  source: DataSource;
}

export const live = <T>(data: T): Sourced<T> => ({ data, source: "live" });
export const fixture = <T>(data: T): Sourced<T> => ({ data, source: "fixture" });

/**
 * Unconfigured falls back to fixtures; a *configured* project that errors does
 * NOT. Swallowing a live failure into fixture data would show plausible fake
 * numbers during an outage, which for this app is the worst possible failure
 * mode — so it throws and app/error.tsx renders the error state (§4.1 item 7).
 */
export function unwrap<T>(
  result: { data: T | null; error: PostgrestError | null },
  what: string,
): T {
  if (result.error) {
    throw new Error(`Supabase read failed (${what}): ${result.error.message}`);
  }
  if (result.data === null) {
    throw new Error(`Supabase read returned no data (${what}).`);
  }
  return result.data;
}
