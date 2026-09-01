import { GameStatusBadge } from "./status-badge";
import { MarketRow } from "./market-row";
import type { GameCloseState, GameGroup } from "@/lib/slate";
import { etClock } from "@/lib/time";

const COLUMNS = [
  "Market",
  "Selection",
  "Odds",
  "Model",
  "Market fair",
  "Edge",
  "Confidence",
  "Stake",
  "",
] as const;

/** One game, rendered as a box score: matchup header, then the market lines. */
export function GameBlock({
  group,
  close,
}: {
  group: GameGroup;
  close: GameCloseState;
}) {
  return (
    <section className="panel">
      <header className="flex flex-wrap items-baseline gap-x-5 gap-y-2 bg-raised px-4 py-3">
        <h3 className="font-display text-2xl uppercase leading-none tracking-[0.01em]">
          <span className="num text-chalk">{group.away.code}</span>
          <span className="mx-2 text-chalk/30">@</span>
          <span className="num text-chalk">{group.home.code}</span>
        </h3>
        <p className="text-[11px] text-chalk/40">
          {group.away.name} at {group.home.name}
        </p>
        <p className="num ml-auto text-[11px] uppercase tracking-placard text-chalk/45">
          {etClock(group.startTimeUtc)} ET
        </p>
        {group.parkName && (
          <p className="w-full text-[11px] text-chalk/30 sm:w-auto">{group.parkName}</p>
        )}
        <div className="w-full sm:w-auto">
          <GameStatusBadge state={close} />
        </div>
      </header>

      <table className="ledger">
        <thead>
          <tr>
            {COLUMNS.map((c, i) => (
              <th key={c || i} scope="col" className={i >= 2 ? "text-right" : undefined}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {group.picks.map((row) => (
            <MarketRow
              key={row.id}
              row={row}
              home={group.home.code}
              away={group.away.code}
            />
          ))}
        </tbody>
      </table>
    </section>
  );
}
