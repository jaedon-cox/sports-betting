"use client";

import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { Circle, Line } from "@visx/shape";

import { useParentWidth } from "@/components/charts/use-parent-width";
import type { CalibrationBucketRow } from "@/lib/types/rows";
import { AXIS, CHART, tickLabel } from "./chart-theme";

/**
 * Reliability diagram. Deliberately not colour-coded by direction: over- and
 * under-confidence are both miscalibration, and tinting one green would
 * suggest otherwise. Dot area is proportional to the bucket's N, so a wild
 * outlier built on 12 picks reads as the small thing it is.
 */
export function CalibrationChart({ rows }: { rows: CalibrationBucketRow[] }) {
  const [ref, width] = useParentWidth();
  const height = 300;
  const m = { top: 12, right: 14, bottom: 30, left: 46 };
  const iw = Math.max(0, width - m.left - m.right);
  const ih = height - m.top - m.bottom;

  const points = rows.filter(
    (r) => r.avg_predicted_prob !== null && r.actual_win_rate !== null,
  );
  if (points.length === 0) {
    return <p className="py-10 text-center text-sm text-chalk/35">No calibration data yet.</p>;
  }

  const maxN = Math.max(...points.map((p) => p.n), 1);
  const x = scaleLinear({ domain: [0, 1], range: [0, iw] });
  const y = scaleLinear({ domain: [0, 1], range: [ih, 0] });

  return (
    <div ref={ref}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Calibration reliability diagram">
          <Group left={m.left} top={m.top}>
            <Line
              from={{ x: x(0), y: y(0) }}
              to={{ x: x(1), y: y(1) }}
              stroke={CHART.threshold}
              strokeDasharray="3,4"
              strokeWidth={1}
            />
            {points.map((p) => (
              <Circle
                key={p.predicted_bucket}
                cx={x(p.avg_predicted_prob as number)}
                cy={y(p.actual_win_rate as number)}
                r={4 + 7 * Math.sqrt(p.n / maxN)}
                fill="rgba(242,238,227,0.16)"
                stroke={CHART.primary}
                strokeWidth={1.25}
              />
            ))}
            <AxisLeft
              scale={y}
              numTicks={5}
              stroke={AXIS.stroke}
              tickStroke={AXIS.stroke}
              tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
              tickLabelProps={() => tickLabel("end", 4)}
            />
            <AxisBottom
              top={ih}
              scale={x}
              numTicks={6}
              stroke={AXIS.stroke}
              tickStroke={AXIS.stroke}
              tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
              tickLabelProps={() => tickLabel("middle", 0, 12)}
            />
          </Group>
        </svg>
      )}
      <p className="mt-2 text-[10px] uppercase tracking-placard text-chalk/35">
        x: predicted · y: observed · dot area ∝ n · dashed line = perfect calibration
      </p>
    </div>
  );
}
