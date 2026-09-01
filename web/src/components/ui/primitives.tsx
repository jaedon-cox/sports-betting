import type { ReactNode } from "react";

/** Section label with a hairline running to the end of the row (§4.2). */
export function Placard({ children }: { children: ReactNode }) {
  return <h2 className="placard mb-3">{children}</h2>;
}

export function PageTitle({
  children,
  kicker,
}: {
  children: ReactNode;
  kicker?: ReactNode;
}) {
  return (
    <div className="mb-8">
      {kicker && (
        <p className="mb-2 text-[11px] uppercase tracking-placard text-chalk/40">
          {kicker}
        </p>
      )}
      <h1 className="font-display text-[clamp(2.4rem,6vw,3.6rem)] uppercase leading-[0.86] tracking-[0.01em]">
        {children}
      </h1>
    </div>
  );
}

export type Tone = "neutral" | "positive" | "negative" | "accent";

const TONE: Record<Tone, string> = {
  neutral: "text-chalk",
  positive: "text-turf",
  negative: "text-clay",
  accent: "text-floodlight",
};

export function toneFor(v: number | null | undefined): Tone {
  if (v === null || v === undefined || v === 0) return "neutral";
  return v > 0 ? "positive" : "negative";
}

/**
 * An aggregate. `n` is required, not optional — the doc's "every aggregate
 * stat shows its N" is enforced by the type, so an N-less rollup cannot be
 * rendered by accident.
 */
export function Stat({
  label,
  value,
  n,
  tone = "neutral",
  unit,
  hint,
}: {
  label: string;
  value: ReactNode;
  n: number;
  tone?: Tone;
  unit?: string;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-placard text-chalk/40">{label}</p>
      <p className={`num mt-1 text-2xl leading-none ${TONE[tone]}`} title={hint}>
        {value}
        {unit && (
          <span className="ml-1.5 align-middle text-[10px] uppercase tracking-placard text-chalk/35">
            {unit}
          </span>
        )}
      </p>
      <p className="num mt-1.5 text-[10px] uppercase tracking-placard text-chalk/30">
        n = {n.toLocaleString("en-US")}
      </p>
    </div>
  );
}

/** A single, non-aggregate figure — no N, because there is nothing to count. */
export function Figure({
  label,
  value,
  tone = "neutral",
  sub,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  sub?: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-placard text-chalk/40">{label}</p>
      <p className={`num mt-1 text-lg leading-none ${TONE[tone]}`}>{value}</p>
      {sub && <p className="mt-1.5 text-[11px] text-chalk/35">{sub}</p>}
    </div>
  );
}

export function Chip({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  const border: Record<Tone, string> = {
    neutral: "border-chalk/20 text-chalk/55",
    positive: "border-turf/45 text-turf",
    negative: "border-clay/45 text-clay",
    accent: "border-floodlight/50 text-floodlight",
  };
  return <span className={`chip ${border[tone]}`}>{children}</span>;
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="panel px-6 py-14 text-center">
      <p className="font-display text-3xl uppercase leading-none text-chalk/80">
        {title}
      </p>
      <div className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-chalk/45">
        {body}
      </div>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
