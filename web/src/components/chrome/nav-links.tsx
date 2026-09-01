"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/record", label: "Record" },
  { href: "/archive", label: "Archive" },
  { href: "/account", label: "Account" },
] as const;

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-6">
      {LINKS.map((link) => {
        const active =
          link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={`border-b-2 pb-0.5 text-[11px] uppercase tracking-placard no-underline transition-colors ${
              active
                ? "border-floodlight text-chalk"
                : "border-transparent text-chalk/45 hover:text-chalk/80"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
