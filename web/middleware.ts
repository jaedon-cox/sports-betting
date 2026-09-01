import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import {
  SUPABASE_ANON_KEY,
  SUPABASE_URL,
  isSupabaseConfigured,
} from "./src/lib/supabase/config";

const PUBLIC_PREFIXES = ["/login", "/auth"];

/**
 * Two jobs (§4.4): refresh the Supabase session cookie on every request, and
 * bounce unauthenticated visitors to /login?next=… before a protected route
 * renders at all — so there is never protected markup on the wire to flash.
 *
 * THIS IS THE ONLY AUTH GATE on the signed-in pages. They deliberately do not
 * re-check the session, because doing so would cost a second auth round-trip
 * per view and would keep them out of the segment cache (§2.3). Anything added
 * to `matcher`'s exclusion list is therefore published to the open internet —
 * widen it only for genuinely public assets.
 *
 * With no Supabase project configured there is no session to check and no
 * live data to protect, so the app runs open on fixtures. Setting the env
 * vars turns the gate on without any other change.
 */
export async function middleware(request: NextRequest) {
  if (!isSupabaseConfigured) return NextResponse.next();

  let response = NextResponse.next({ request });

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(list) {
        for (const { name, value } of list) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of list) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PREFIXES.some((p) => path.startsWith(p));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", `${path}${request.nextUrl.search}`);
    return NextResponse.redirect(url);
  }

  if (user && path.startsWith("/login")) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|webp)$).*)"],
};
