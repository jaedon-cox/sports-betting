import Link from "next/link";

import { NavLinks } from "./nav-links";

/**
 * No per-user data by design — see app/layout.tsx. The reader's email lives on
 * /account, the one page that is never cached.
 */
export function SiteHeader() {
  return (
    <header className="rule-b bg-surface/70 backdrop-blur">
      <div className="mx-auto flex max-w-ledger flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-baseline gap-2 no-underline">
          <span className="h-1.5 w-1.5 translate-y-[-2px] bg-floodlight" aria-hidden />
          <span className="font-display text-2xl uppercase leading-none tracking-[0.02em] text-chalk">
            Night Ledger
          </span>
        </Link>
        <NavLinks />
        <div className="ml-auto">
          <form action="/auth/signout" method="post">
            <button type="submit" className="btn-ghost">
              Sign out
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
