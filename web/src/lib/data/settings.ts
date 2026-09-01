import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";
import type { UserSettingsRow } from "@/lib/types/rows";
import { fixture, live, type Sourced } from "./source";

/**
 * The only user-writable relation in the schema (db/policies/003). Note
 * bankroll_usd is READ but never written here: §5 is percent-only, and the
 * bankroll input is a display-time convenience held in the browser
 * (components/bankroll/) so it can never rewrite a historical stake.
 */
export async function getUserSettings(
  userId: string,
): Promise<Sourced<UserSettingsRow | null>> {
  if (!isSupabaseConfigured) {
    const now = new Date().toISOString();
    return fixture({
      user_id: userId,
      bankroll_usd: 0,
      notify_email: true,
      created_at: now,
      updated_at: now,
    });
  }

  // UNTAGGED on purpose: this row is per-user under RLS auth.uid(), so it must
  // never enter the shared Data Cache. See lib/supabase/server.ts.
  const supabase = createServerSupabase();
  const { data, error } = await supabase
    .from("user_settings")
    .select("*")
    .eq("user_id", userId)
    .maybeSingle();
  if (error) {
    throw new Error(`Supabase read failed (user_settings): ${error.message}`);
  }
  return live(data);
}

export interface WriteResult {
  ok: boolean;
  message: string;
}

export async function setNotifyEmail(
  userId: string,
  notify: boolean,
): Promise<WriteResult> {
  if (!isSupabaseConfigured) {
    return {
      ok: false,
      message: "Not saved: no Supabase project is configured for this deployment.",
    };
  }
  const supabase = createServerSupabase();
  const { error } = await supabase
    .from("user_settings")
    .upsert({ user_id: userId, notify_email: notify }, { onConflict: "user_id" });
  return error
    ? { ok: false, message: `Could not save: ${error.message}` }
    : { ok: true, message: "Notification preference saved." };
}
