/**
 * There is no Supabase project yet. Everything downstream branches on this
 * one predicate: configured -> real reads against the real view names;
 * unconfigured -> typed fixtures, and the UI says so. Wiring a project later
 * is setting two env vars, not editing a component.
 */
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const isSupabaseConfigured =
  SUPABASE_URL.length > 0 && SUPABASE_ANON_KEY.length > 0;

/** Absolute origin for magic-link redirects; Vercel supplies VERCEL_URL. */
export function siteOrigin(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  const vercel = process.env.VERCEL_URL;
  if (vercel) return `https://${vercel}`;
  return "http://localhost:3000";
}
