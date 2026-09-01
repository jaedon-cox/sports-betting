"use client";

import { formatUsd } from "@/lib/format";
import { useBankroll } from "./bankroll-context";

export function BankrollInput() {
  const { bankroll, setBankroll, ready } = useBankroll();
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-placard text-chalk/40">
        Display bankroll
      </span>
      <span className="mt-1 flex items-center gap-2">
        <span className="num text-chalk/35">$</span>
        <input
          type="number"
          min={0}
          step={50}
          inputMode="decimal"
          placeholder="—"
          disabled={!ready}
          value={bankroll ?? ""}
          onChange={(e) => {
            const v = Number(e.target.value);
            setBankroll(e.target.value === "" || !Number.isFinite(v) || v <= 0 ? null : v);
          }}
          className="field num w-32 py-1 text-right"
          aria-describedby="bankroll-note"
        />
      </span>
      <span id="bankroll-note" className="mt-1.5 block text-[10px] text-chalk/30">
        Stays in this browser. Never saved to your account, never applied to history.
      </span>
    </label>
  );
}

/** The dollar rendering of a Kelly percentage. Absent until a bankroll is set. */
export function StakeAmount({ kelly }: { kelly: number }) {
  const { bankroll } = useBankroll();
  if (bankroll === null || kelly <= 0) return null;
  return (
    <span className="num ml-2 text-[11px] text-chalk/35">
      ≈ {formatUsd(bankroll * kelly)}
    </span>
  );
}
