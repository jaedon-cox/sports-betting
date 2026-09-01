import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-ledger px-4 py-10 sm:px-6 lg:px-8">
      <div className="panel px-6 py-14 text-center">
        <p className="font-display text-4xl uppercase leading-none text-chalk/70">
          No such page
        </p>
        <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-chalk/45">
          That pick or page is not in the record.
        </p>
        <Link href="/" className="btn-ghost mt-8 no-underline">
          Back to today&rsquo;s board
        </Link>
      </div>
    </main>
  );
}
