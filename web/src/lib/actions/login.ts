"use server";

import { isSupabaseConfigured, siteOrigin } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";

export type LoginState =
  | { status: "idle" }
  | { status: "unconfigured"; message: string }
  | { status: "sent"; message: string }
  | { status: "error"; message: string };

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Invite-only magic link (§4.4). shouldCreateUser:false is the enforcement
 * point — with self-serve signup disabled in Supabase Auth, an address with
 * no invite simply has no account and no link is issued.
 *
 * The response is deliberately identical whether or not the address exists:
 * an invite-only system that says "no such user" is an invitee-list oracle.
 */
export async function requestMagicLink(
  _prev: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const next = String(formData.get("next") ?? "/");

  if (!EMAIL.test(email)) {
    return { status: "error", message: "Enter a valid email address." };
  }

  if (!isSupabaseConfigured) {
    return {
      status: "unconfigured",
      message:
        "No Supabase project is wired to this deployment, so no link can be sent. The app is serving fixture data.",
    };
  }

  const supabase = createServerSupabase();
  const redirectTo = `${siteOrigin()}/auth/callback?next=${encodeURIComponent(next)}`;
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { shouldCreateUser: false, emailRedirectTo: redirectTo },
  });

  if (error && error.status === 429) {
    return { status: "error", message: "Too many requests. Try again in a few minutes." };
  }

  return {
    status: "sent",
    message: `If ${email} has an invite, a sign-in link is on its way. The link expires in one hour.`,
  };
}
