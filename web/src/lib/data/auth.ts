import { redirect } from "next/navigation";

import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";

export interface SessionUser {
  id: string;
  email: string | null;
  /** True when there is no Supabase project and the app is running on fixtures. */
  isDemo: boolean;
}

const DEMO_USER: SessionUser = {
  id: "00000000-0000-0000-0000-000000000000",
  email: "demo@localhost",
  isDemo: true,
};

export async function getSessionUser(): Promise<SessionUser | null> {
  // Unconfigured: there is no auth to check and no data worth protecting.
  // The real guard below is unchanged; only this early return is env-gated.
  if (!isSupabaseConfigured) return DEMO_USER;

  const supabase = createServerSupabase();
  // getUser(), not getSession(): getSession trusts the cookie, getUser
  // revalidates the JWT with the auth server.
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return null;
  return { id: data.user.id, email: data.user.email ?? null, isDemo: false };
}

/**
 * Server-side gate for protected routes (§4.4). Because this runs during the
 * server render, an unauthenticated visitor never receives protected markup —
 * there is no client-side flash to suppress.
 */
export async function requireUser(nextPath: string): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) redirect(`/login?next=${encodeURIComponent(nextPath)}`);
  return user;
}
