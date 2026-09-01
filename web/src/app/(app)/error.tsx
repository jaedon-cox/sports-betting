"use client";

import { useEffect } from "react";

import { ErrorPanel } from "@/components/ui/error-panel";

/** Nested boundary so a failed read keeps the nav instead of stranding the reader. */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return <ErrorPanel digest={error.digest} onReset={reset} />;
}
