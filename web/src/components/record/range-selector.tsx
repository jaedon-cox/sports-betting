import Link from "next/link";

import { RANGES, type RangeKey } from "@/lib/data/record";

/** Links, not a client control: the window belongs in the URL so it can be shared. */
export function RangeSelector({ active }: { active: RangeKey }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-[10px] uppercase tracking-placard text-chalk/35">Window</span>
      <div className="flex border" style={{ borderColor: "rgba(242,238,227,0.22)" }}>
        {(Object.keys(RANGES) as RangeKey[]).map((key) => (
          <Link
            key={key}
            href={`/record?range=${key}`}
            aria-current={key === active ? "true" : undefined}
            className={`px-3 py-1.5 text-[11px] uppercase tracking-placard no-underline transition-colors ${
              key === active ? "bg-floodlight text-ink" : "text-chalk/50 hover:text-chalk"
            }`}
          >
            {RANGES[key].label}
          </Link>
        ))}
      </div>
    </div>
  );
}
