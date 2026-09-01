/**
 * Scoped to /record rather than the app root: a root-level loading boundary
 * flushes a 200 shell before the page runs, which turns notFound() on
 * /picks/[id] into a soft 404. This route never calls notFound().
 */
export default function Loading() {
  return (
    <p className="py-24 text-center text-[11px] uppercase tracking-placard text-chalk/30">
      Reading the ledger…
    </p>
  );
}
