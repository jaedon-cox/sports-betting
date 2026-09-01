/**
 * There is no Supabase project yet. Rather than render fake numbers silently,
 * the app says so on every page — a plausible-looking edge that came from a
 * fixture is the single most dangerous thing this UI could show.
 */
export function FixtureBanner() {
  return (
    <div className="border-b border-floodlight/30 bg-floodlight/10">
      <p className="mx-auto max-w-ledger px-4 py-2 text-[11px] uppercase tracking-placard text-floodlight sm:px-6 lg:px-8">
        Fixture data · no database connected · every figure below is illustrative
      </p>
    </div>
  );
}
