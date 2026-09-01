"use client";

import { Group } from "@visx/group";
import { scaleLinear, scaleTime } from "@visx/scale";
import { Line, LinePath } from "@visx/shape";

import { useParentWidth } from "@/components/charts/use-parent-width";
import type { RoiCurveRow } from "@/lib/types/rows";
import { CHART } from "./chart-theme";

/**
 * Intentionally the smallest module on the page (§4.1). ROI is not the gate
 * metric — under a couple of thousand bets it is mostly variance — so it gets
 * a muted sparkline and a plain-language disclaimer rather than a headline
 * number, no matter how good it looks on any given day.
 */
export function RoiCurve({ rows }: { rows: RoiCurveRow[] }) {
  const [ref, width] = useParentWidth();
  const height = 96;

  const points = rows
    .filter((r) => r.cum_roi_pct !== null)
    .map((r) => ({ x: new Date(`${r.rollup_date}T12:00:00Z`), y: r.cum_roi_pct as number }));

  if (points.length < 2) {
    return <p className="text-xs text-chalk/35">Not enough settled days to draw a curve.</p>;
  }

  const xs = points.map((p) => p.x.getTime());
  const ys = points.map((p) => p.y);
  const pad = (Math.max(...ys) - Math.min(...ys)) * 0.2 || 0.02;
  const x = scaleTime({ domain: [Math.min(...xs), Math.max(...xs)], range: [0, Math.max(0, width - 2)] });
  const y = scaleLinear({
    domain: [Math.min(...ys, 0) - pad, Math.max(...ys, 0) + pad],
    range: [height - 8, 8],
  });

  return (
    <div ref={ref}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Cumulative return on staked units">
          <Group left={1}>
            <Line
              from={{ x: 0, y: y(0) }}
              to={{ x: width - 2, y: y(0) }}
              stroke={CHART.threshold}
              strokeDasharray="3,4"
              strokeWidth={1}
            />
            <LinePath
              data={points}
              x={(p) => x(p.x)}
              y={(p) => y(p.y)}
              stroke={CHART.muted}
              strokeWidth={1.5}
            />
          </Group>
        </svg>
      )}
    </div>
  );
}
