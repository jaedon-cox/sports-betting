import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { DATA_TTL_SECONDS, type CacheTag } from "@/lib/cache";
import type { Database } from "@/lib/types/database";
import { SUPABASE_ANON_KEY, SUPABASE_URL, isSupabaseConfigured } from "./config";

/** Next augments RequestInit with `next`; name it rather than reach for `any`. */
type CachedInit = RequestInit & {
  next?: { tags?: string[]; revalidate?: number | false };
};

/**
 * Server-Component / Route-Handler client, RLS-scoped to the caller's session
 * (§4.3: no custom REST server for reads). Callers must check
 * `isSupabaseConfigured` first — this throws rather than silently producing a
 * client that points at nothing.
 */
export function createServerSupabase(tags?: readonly CacheTag[]) {
  if (!isSupabaseConfigured) {
    throw new Error(
      "Supabase is not configured; call isSupabaseConfigured before createServerSupabase.",
    );
  }
  const store = cookies();
  return createServerClient<Database>(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return store.getAll();
      },
      setAll(list) {
        try {
          for (const { name, value, options } of list) {
            store.set(name, value, options);
          }
        } catch {
          // Server Components cannot mutate cookies. Session refresh happens
          // in middleware.ts, so a failure here is expected and harmless.
        }
      },
    },
    ...(tags ? { global: { fetch: taggedFetch(tags) } } : {}),
  });
}

/**
 * Puts PostgREST GETs into Next's Data Cache under `tags`, so a page view
 * costs a Supabase request only after a publish invalidates them (§2.3).
 *
 * THE BOUNDARY THAT MATTERS: this is only ever passed for relations whose RLS
 * is `USING (true)` for `authenticated` — every signed-in reader sees byte-
 * identical rows, so a shared cache entry can leak nothing between users.
 * user_settings is per-user under `auth.uid()` and must NEVER be read through
 * a tagged client; lib/data/settings.ts calls createServerSupabase() with no
 * tags for exactly that reason.
 *
 * Auth traffic is excluded by URL: only /rest/v1/ is cacheable, so a token
 * refresh can never be served from cache.
 */
function taggedFetch(tags: readonly CacheTag[]) {
  return (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;

    if (!url.includes("/rest/v1/")) {
      return fetch(input, { ...init, cache: "no-store" });
    }
    const cached: CachedInit = {
      ...init,
      next: { tags: [...tags], revalidate: DATA_TTL_SECONDS },
    };
    return fetch(input, cached);
  };
}

export type Db = ReturnType<typeof createServerSupabase>;
