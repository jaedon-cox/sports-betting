import { type EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * Handles both magic-link shapes so the deployment works whichever way the
 * Supabase email template is configured: `?code=` (PKCE, the default for
 * @supabase/ssr) and `?token_hash=&type=` (the {{ .TokenHash }} template).
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const next = url.searchParams.get("next") ?? "/";
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/";

  if (!isSupabaseConfigured) {
    return NextResponse.redirect(new URL("/login?error=unconfigured", url.origin));
  }

  const supabase = createServerSupabase();
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;

  const result = code
    ? await supabase.auth.exchangeCodeForSession(code)
    : tokenHash && type
      ? await supabase.auth.verifyOtp({ token_hash: tokenHash, type })
      : { error: { message: "missing credentials" } };

  if (result.error) {
    return NextResponse.redirect(new URL("/login?error=link", url.origin));
  }
  return NextResponse.redirect(new URL(safeNext, url.origin));
}
