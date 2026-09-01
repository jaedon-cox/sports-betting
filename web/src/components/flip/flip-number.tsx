"use client";

import { useEffect, useState } from "react";

import { FlipDigit } from "./flip-digit";

const isDigit = (c: string) => c >= "0" && c <= "9";

/**
 * The signature moment (§4.2): headline figures land like a ballpark board.
 * Reserved for today's exposure and the season record — used on a third
 * number it becomes decoration rather than a signal.
 *
 * The server renders the final value, so the figure is correct before any
 * JavaScript runs; the flip only replays it. The scramble is index-derived,
 * not random, so there is nothing to mismatch at hydration.
 */
export function FlipNumber({
  value,
  label,
  className = "",
}: {
  value: string;
  label: string;
  className?: string;
}) {
  const finals = [...value];
  const [chars, setChars] = useState<string[]>(finals);

  useEffect(() => {
    const target = [...value];
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setChars(target);
      return;
    }

    // Each flap settles two ticks after the one to its left, so the number
    // resolves left-to-right the way a mechanical board does.
    const settleAt = target.map((c, i) => (isDigit(c) ? 4 + i * 2 : 0));
    const last = Math.max(0, ...settleAt);
    let tick = 0;

    const step = () => {
      setChars(
        target.map((c, i) =>
          tick >= (settleAt[i] ?? 0) ? c : String((tick + i * 3) % 10),
        ),
      );
    };
    step();

    const timer = setInterval(() => {
      tick += 1;
      step();
      if (tick > last) clearInterval(timer);
    }, 85);
    return () => clearInterval(timer);
  }, [value]);

  return (
    <span className={`inline-flex items-baseline font-mono ${className}`}>
      {/* Screen readers get the settled figure once, not every intermediate frame. */}
      <span className="sr-only">{`${label}: ${value}`}</span>
      {chars.map((c, i) =>
        isDigit(c) ? (
          <FlipDigit key={i} char={c} />
        ) : (
          <span key={i} aria-hidden className="px-[0.02em]">
            {c}
          </span>
        ),
      )}
    </span>
  );
}
