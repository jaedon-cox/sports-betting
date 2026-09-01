/**
 * The error state (§4.1 item 7). It deliberately does not fall back to
 * anything that looks like data: a page that quietly renders plausible numbers
 * during a database outage is worse than a page that says it is broken.
 */
export function ErrorPanel({
  digest,
  onReset,
}: {
  digest?: string;
  onReset: () => void;
}) {
  return (
    <div className="panel px-6 py-14 text-center">
      <p className="font-display text-4xl uppercase leading-none text-clay">
        Board unavailable
      </p>
      <p className="mx-auto mt-4 max-w-lg text-sm leading-relaxed text-chalk/50">
        A read failed, so nothing is being shown rather than something
        approximate. No numbers on this page are stale or invented — there are
        simply none.
      </p>
      {digest && (
        <p className="num mt-4 text-[11px] uppercase tracking-placard text-chalk/25">
          ref {digest}
        </p>
      )}
      <button type="button" onClick={onReset} className="btn-primary mt-8">
        Try again
      </button>
    </div>
  );
}
