import { LoginForm } from "@/components/auth/login-form";

export const metadata = { title: "Sign in" };

const ERRORS: Record<string, string> = {
  link: "That sign-in link has expired or was already used. Request a new one.",
  unconfigured: "This deployment has no Supabase project attached, so links cannot be verified.",
};

export default function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string; error?: string };
}) {
  // Only same-origin paths survive: an open redirect through `next` would let
  // a crafted link bounce an authenticated user off-site.
  const raw = searchParams.next ?? "/";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
  const error = searchParams.error ? ERRORS[searchParams.error] : undefined;

  return (
    <main className="mx-auto max-w-md px-4 py-16 sm:px-6">
      <p className="text-[11px] uppercase tracking-placard text-chalk/40">
        Invite only
      </p>
      <h1 className="mt-2 font-display text-[clamp(2.6rem,8vw,3.6rem)] uppercase leading-[0.86]">
        Night
        <br />
        Ledger
      </h1>
      <p className="mt-4 text-sm leading-relaxed text-chalk/50">
        No passwords. Enter the address your invite was sent to and a one-time
        sign-in link comes back by email.
      </p>

      {error && (
        <p className="mt-6 border border-clay/40 px-3 py-2 text-xs text-clay">{error}</p>
      )}

      <div className="mt-8">
        <LoginForm next={next} />
      </div>
    </main>
  );
}
