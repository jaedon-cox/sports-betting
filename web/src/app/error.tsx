"use client";

import { useEffect } from "react";

import { ErrorPanel } from "@/components/ui/error-panel";

/** Root boundary: covers /login and anything outside the signed-in group. */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto w-full max-w-ledger px-4 py-10 sm:px-6 lg:px-8">
      <ErrorPanel digest={error.digest} onReset={reset} />
    </main>
  );
}
