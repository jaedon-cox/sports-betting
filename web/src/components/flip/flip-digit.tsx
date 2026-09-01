"use client";

import { useEffect, useState } from "react";

/**
 * One flap on the board. The static halves always carry the settled
 * character, so with JavaScript disabled — or with prefers-reduced-motion,
 * which hides the folds in CSS — the digit is simply readable.
 */
export function FlipDigit({ char }: { char: string }) {
  const [pair, setPair] = useState({ prev: char, next: char });
  const [seq, setSeq] = useState(0);

  useEffect(() => {
    if (pair.next === char) return;
    setPair({ prev: pair.next, next: char });
    setSeq((s) => s + 1);
    const settle = setTimeout(() => setPair({ prev: char, next: char }), 270);
    return () => clearTimeout(settle);
  }, [char, pair.next]);

  const folding = pair.prev !== pair.next;

  return (
    <span className="flap" aria-hidden>
      <span className="flap__half fl-top">
        <i>{pair.next}</i>
      </span>
      <span className="flap__half fl-bot">
        <i>{folding ? pair.prev : pair.next}</i>
      </span>
      {folding && (
        <>
          <span key={`out-${seq}`} className="flap__fold fl-top">
            <i>{pair.prev}</i>
          </span>
          <span key={`in-${seq}`} className="flap__fold fl-bot">
            <i>{pair.next}</i>
          </span>
        </>
      )}
    </span>
  );
}
