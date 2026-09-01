import Link from "next/link";

import type { SlateScope } from "@/lib/slate";

/**
 * Defaults to ALL EVALUATED, not recommended-only (§4.1) — the model's
 * declined games are part of the CLV record, so hiding them by default would
 * misrepresent the track record. Rendered as links rather than a client
 * control so the choice survives a reload and needs no JavaScript, and the
 * active scope is always spelled out rather than implied by a highlight.
 */
export function ScopeToggle({
  scope,
  nEvaluated,
  nRecommended,
}: {
  scope: SlateScope;
  nEvaluated: number;
  nRecommended: number;
}) {
  const options: { key: SlateScope; label: string; n: number; href: string }[] = [
    { key: "all", label: "All evaluated", n: nEvaluated, href: "/" },
    { key: "recommended", label: "Recommended only", n: nRecommended, href: "/?scope=recommended" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-[10px] uppercase tracking-placard text-chalk/35">
        Showing
      </span>
      <div className="flex border" style={{ borderColor: "rgba(242,238,227,0.22)" }}>
        {options.map((o) => (
          <Link
            key={o.key}
            href={o.href}
            aria-current={o.key === scope ? "true" : undefined}
            className={`px-3 py-1.5 text-[11px] uppercase tracking-placard no-underline transition-colors ${
              o.key === scope
                ? "bg-floodlight text-ink"
                : "text-chalk/50 hover:text-chalk"
            }`}
          >
            {o.label}
            <span className="num ml-2 opacity-70">{o.n}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
