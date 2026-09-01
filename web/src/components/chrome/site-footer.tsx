export function SiteFooter() {
  return (
    <footer className="rule-t mt-16">
      <div className="mx-auto max-w-ledger px-4 py-8 sm:px-6 lg:px-8">
        <p className="max-w-3xl text-xs leading-relaxed text-chalk/40">
          For research and record-keeping. Nothing here is betting advice. A
          positive closing-line edge is a measure of pricing skill, not a
          prediction of profit, and no model removes the risk of loss. Bet only
          what you can afford to lose. If gambling stops being a choice, call
          1-800-GAMBLER or visit{" "}
          <a
            href="https://www.ncpgambling.org/help-treatment/"
            className="text-chalk/60 underline hover:text-chalk"
            rel="noreferrer noopener"
            target="_blank"
          >
            ncpgambling.org
          </a>
          .
        </p>
        <p className="mt-4 text-[10px] uppercase tracking-placard text-chalk/25">
          Stakes are expressed as a percentage of bankroll. No dollar amount is
          ever stored.
        </p>
      </div>
    </footer>
  );
}
