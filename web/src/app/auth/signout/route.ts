import { NextResponse, type NextRequest } from "next/server";

import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";

/** POST-only: a GET sign-out is trivially triggerable by a third-party image tag. */
export async function POST(request: NextRequest) {
  if (isSupabaseConfigured) {
    await createServerSupabase().auth.signOut();
  }
  return NextResponse.redirect(new URL("/login", new URL(request.url).origin), {
    status: 303,
  });
}
