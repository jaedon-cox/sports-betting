import { CLV_UNIT, clvSign, formatClv, type ClvMeasure } from "@/lib/clv";

/**
 * The only component that renders a CLV number. Two definitions of CLV are
 * live in the schema at once (see lib/clv.ts), so every figure carries the
 * unit it is measured in — and the two use different notation (bps vs. %) so
 * they cannot be conflated even at a glance.
 */
export function ClvValue({
  measure,
  showUnit = true,
  className = "",
}: {
  measure: ClvMeasure | null;
  showUnit?: boolean;
  className?: string;
}) {
  const sign = clvSign(measure);
  const tone =
    sign > 0 ? "text-turf" : sign < 0 ? "text-clay" : "text-chalk/55";
  const unit = measure ? CLV_UNIT[measure.kind] : null;

  return (
    <span className={`num whitespace-nowrap ${tone} ${className}`} title={unit?.note}>
      {formatClv(measure)}
      {showUnit && unit && (
        <span className="ml-1 text-[10px] uppercase tracking-placard text-chalk/30">
          {unit.tag}
        </span>
      )}
    </span>
  );
}

/** Footnote used wherever both definitions appear on the same page. */
export function ClvUnitsNote() {
  return (
    <p className="mt-3 text-[11px] leading-relaxed text-chalk/35">
      <span className="uppercase tracking-placard text-chalk/45">Two CLV units.</span>{" "}
      {CLV_UNIT.absolute.note} {CLV_UNIT.relative.note} They are roughly 2×
      apart at typical prices and are never averaged together.
    </p>
  );
}
