import { SiteHeader } from "@/components/chrome/site-header";

/**
 * Chrome for the signed-in surfaces. Static by construction: middleware.ts is
 * what proves the reader is signed in, so this layout never needs to ask, and
 * every page under it stays eligible for the segment cache.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-ledger px-4 py-10 sm:px-6 lg:px-8">
        {children}
      </main>
    </>
  );
}
