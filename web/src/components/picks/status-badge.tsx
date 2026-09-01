import { ClvValue } from "@/components/clv/clv-value";
import { Chip } from "@/components/ui/primitives";
import { absolute, clvSign } from "@/lib/clv";
import type { GameCloseState } from "@/lib/slate";

/**
 * Closing times stagger across a slate (§4.1), so the badge is per game, not
 * per page. Pre-close there is no CLV to report yet; post-close the number
 * shown is the mean ABSOLUTE live CLV across the game's markets — labelled as
 * such, with its N, because it is an average of several picks.
 */
export function GameStatusBadge({ state }: { state: GameCloseState }) {
  if (!state.closed || state.meanAbsoluteClv === null) {
    return <Chip>Line open</Chip>;
  }
  const measure = absolute(state.meanAbsoluteClv);
  const sign = clvSign(measure);
  return (
    <span className="inline-flex items-center gap-2">
      <Chip tone={sign > 0 ? "positive" : sign < 0 ? "negative" : "neutral"}>
        Closed
      </Chip>
      <span className="text-[10px] uppercase tracking-placard text-chalk/35">
        CLV
      </span>
      <ClvValue measure={measure} className="text-sm" />
      <span className="num text-[10px] uppercase tracking-placard text-chalk/30">
        n = {state.n}
      </span>
    </span>
  );
}
