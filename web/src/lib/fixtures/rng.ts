/**
 * Deterministic PRNG so fixture history is byte-identical across renders and
 * between server and client — a Math.random() fixture would hydrate-mismatch
 * and make every chart jitter on refresh.
 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const round = (v: number, dp: number): number =>
  Number(v.toFixed(dp));

/** Picks an element deterministically. */
export function pick<T>(rand: () => number, xs: readonly T[]): T {
  return xs[Math.floor(rand() * xs.length)] as T;
}
