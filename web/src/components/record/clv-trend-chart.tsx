"use client";

import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { scaleLinear, scaleTime } from "@visx/scale";
import { Line, LinePath } from "@visx/shape";

import { useParentWidth } from "@/components/charts/use-parent-width";
import { CLV_UNIT } from "@/lib/clv";
import type { ClvTrendRow } from "@/lib/types/rows";
import { AXIS, CHART, tickLabel } from "./chart-theme";

/**
 * Cumulative CLV, the gate metric. Plotted in RELATIVE units because that is
 * what mv_clv_trend stores; the axis says so. The break-even line is the only
 * thing on this chart drawn in Floodlight — it is the threshold the whole
 * project is measured against.
 */
export function ClvTrendChart({
  rows,
  blended,
}: {
  rows: ClvTrendRow[];
  blended: string;
}) {
  const [ref, width] = useParentWidth();
  const height = 300;
  const m = { top: 12, right: 12, bottom: 28, left: 52 };
  const iw = Math.max(0, width - m.left - m.right);
  const ih = height - m.top - m.bottom;

  const markets = [...new Set(rows.map((r) => r.market))].filter((x) => x !== blended).sort();
  const series = [blended, ...markets].map((market) => ({
    market,
    points: rows
      .filter((r) => r.market === market && r.cum_avg_clv_pct !== null)
      .map((r) => ({ x: new Date(`${r.rollup_date}T12:00:00Z`), y: r.cum_avg_clv_pct as number })),
  }));

  const all = series.flatMap((s) => s.points);
  if (all.length === 0) {
    return <p className="py-10 text-center text-sm text-chalk/35">No settled picks in this window.</p>;
  }

  const xs = all.map((p) => p.x.getTime());
  const ys = all.map((p) => p.y);
  const pad = (Math.max(...ys) - Math.min(...ys)) * 0.15 || 0.01;

  const x = scaleTime({ domain: [Math.min(...xs), Math.max(...xs)], range: [0, iw] });
  const y = scaleLinear({
    domain: [Math.min(...ys, 0) - pad, Math.max(...ys, 0) + pad],
    range: [ih, 0],
    nice: true,
  });

  return (
    <div ref={ref}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Cumulative closing line value by market">
          <Group left={m.left} top={m.top}>
            <Line
              from={{ x: 0, y: y(0) }}
              to={{ x: iw, y: y(0) }}
              stroke={CHART.threshold}
              strokeDasharray="3,4"
              strokeWidth={1}
            />
            {series.map((s, i) => (
              <LinePath
                key={s.market}
                data={s.points}
                x={(p) => x(p.x)}
                y={(p) => y(p.y)}
                stroke={i === 0 ? CHART.primary : CHART.muted}
                strokeWidth={i === 0 ? 2 : 1}
                strokeDasharray={i === 0 ? undefined : CHART.dashes[(i - 1) % CHART.dashes.length]}
              />
            ))}
            <AxisLeft
              scale={y}
              numTicks={5}
              stroke={AXIS.stroke}
              tickStroke={AXIS.stroke}
              tickFormat={(v) => `${(Number(v) * 100).toFixed(1)}%`}
              tickLabelProps={() => tickLabel("end", 4)}
            />
            <AxisBottom
              top={ih}
              scale={x}
              numTicks={Math.max(2, Math.floor(iw / 110))}
              stroke={AXIS.stroke}
              tickStroke={AXIS.stroke}
              tickLabelProps={() => tickLabel("middle", 0, 12)}
            />
          </Group>
        </svg>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] uppercase tracking-placard text-chalk/40">
        <span className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-6" style={{ background: CHART.primary }} />
          {blended}
        </span>
        {markets.map((mk, i) => (
          <span key={mk} className="flex items-center gap-2">
            <svg width="24" height="2" aria-hidden>
              <line
                x1="0" y1="1" x2="24" y2="1"
                stroke={CHART.muted}
                strokeDasharray={CHART.dashes[i % CHART.dashes.length]}
              />
            </svg>
            {mk}
          </span>
        ))}
        <span className="ml-auto normal-case tracking-normal text-chalk/30">
          y-axis: {CLV_UNIT.relative.axis}
        </span>
      </div>
    </div>
  );
}
