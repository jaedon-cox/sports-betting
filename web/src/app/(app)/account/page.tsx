import { BankrollProvider } from "@/components/bankroll/bankroll-context";
import { BankrollInput } from "@/components/bankroll/bankroll-ui";
import { NotifyForm } from "@/components/account/notify-form";
import { PageTitle, Placard } from "@/components/ui/primitives";
import { requireUser } from "@/lib/data/auth";
import { getUserSettings } from "@/lib/data/settings";

/**
 * The one page whose output differs per reader: it reads user_settings under
 * RLS `auth.uid()`. force-dynamic is load-bearing here — a cached render would
 * serve one account's preferences to another. lib/data/settings.ts also reads
 * it through an UNTAGGED Supabase client so the row never enters the shared
 * Data Cache.
 */
export const dynamic = "force-dynamic";
export const metadata = { title: "Account" };

export default async function AccountPage() {
  const user = await requireUser("/account");
  const { data: settings } = await getUserSettings(user.id);

  return (
    <>
      <PageTitle kicker={user.email ?? "Signed in"}>Account</PageTitle>

      <section className="mb-10">
        <Placard>Notifications</Placard>
        <div className="panel px-4 py-6">
          <NotifyForm initial={settings?.notify_email ?? true} />
          {user.isDemo && (
            <p className="mt-4 text-[11px] text-chalk/35">
              This deployment has no database attached, so preferences cannot be
              saved yet.
            </p>
          )}
        </div>
      </section>

      <section className="mb-10">
        <Placard>Display bankroll</Placard>
        <div className="panel px-4 py-6">
          <BankrollProvider>
            <div className="max-w-xs">
              <BankrollInput />
            </div>
          </BankrollProvider>
          <p className="mt-5 max-w-2xl text-[11px] leading-relaxed text-chalk/35">
            Stakes are recorded as a fraction of bankroll and nothing else. This
            figure only converts today&rsquo;s percentages into dollars while you
            read them; it is kept in this browser, is never sent to the server,
            and can never restate a historical stake. Change it whenever you
            like — the record does not move.
          </p>
        </div>
      </section>

      <section>
        <Placard>Session</Placard>
        <div className="panel flex flex-wrap items-center justify-between gap-4 px-4 py-6">
          <p className="text-sm text-chalk/55">
            Signed in as <span className="num text-chalk">{user.email ?? "—"}</span>
          </p>
          <form action="/auth/signout" method="post">
            <button type="submit" className="btn-primary">
              Sign out
            </button>
          </form>
        </div>
      </section>
    </>
  );
}
