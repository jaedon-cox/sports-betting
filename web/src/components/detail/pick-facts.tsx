import { Chip, Figure } from "@/components/ui/primitives";
import { TIER_LABEL, confidenceTier } from "@/lib/confidence";
import {
  formatAmericanOdds,
  formatPercent,
  formatProbability,
  formatSignedPercent,
  humanize,
} from "@/lib/format";
import { etStamp } from "@/lib/time";
import type { PickArchiveRow } from "@/lib/types/rows";

export function PickFacts({ pick }: { pick: PickArchiveRow }) {
  const tier = confidenceTier(pick.edge_pct);
  return (
    <div className="panel grid gap-6 px-4 py-6 sm:grid-cols-3 lg:grid-cols-4">
      <Figure label="Market" value={humanize(pick.market)} sub={`Book: ${pick.book}`} />
      <Figure label="Quoted odds" value={formatAmericanOdds(pick.market_odds_american)} />
      <Figure label="Model probability" value={formatProbability(pick.model_prob, 2)} />
      <Figure
        label="Market fair probability"
        value={formatProbability(pick.market_fair_prob, 2)}
        sub="de-vigged"
      />
      <Figure
        label="Edge"
        value={formatSignedPercent(pick.edge_pct)}
        tone={
          pick.edge_pct === null || pick.edge_pct === 0
            ? "neutral"
            : pick.edge_pct > 0
              ? "positive"
              : "negative"
        }
        sub={tier ? TIER_LABEL[tier] : "below threshold"}
      />
      <Figure
        label="Stake"
        value={
          pick.kelly_stake_fraction > 0 ? formatPercent(pick.kelly_stake_fraction) : "—"
        }
        sub="% of bankroll"
      />
      <Figure label="Locked at" value={etStamp(pick.pick_locked_at)} />
      <div>
        <p className="text-[10px] uppercase tracking-placard text-chalk/40">Status</p>
        <p className="mt-2">
          {pick.recommended ? (
            <Chip tone="accent">Recommended</Chip>
          ) : (
            <Chip>Evaluated, not bet</Chip>
          )}
        </p>
        <p className="mt-2 text-[11px] text-chalk/35">
          Game: {humanize(pick.game_status)}
        </p>
      </div>
    </div>
  );
}
