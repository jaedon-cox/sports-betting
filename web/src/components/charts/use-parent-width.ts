"use client";

import { useEffect, useRef, useState } from "react";

/**
 * visx needs pixel dimensions. A ResizeObserver keeps that honest without
 * pulling in another package, and 0 width (pre-measure or SSR) is the signal
 * to render nothing rather than a squashed chart.
 */
export function useParentWidth(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width ?? 0;
      setWidth(Math.floor(next));
    });
    observer.observe(el);
    setWidth(Math.floor(el.getBoundingClientRect().width));
    return () => observer.disconnect();
  }, []);

  return [ref, width];
}
