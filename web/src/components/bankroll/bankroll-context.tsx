"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

/**
 * Display-only bankroll (§4.1, §5). It drives today's dollar column and
 * nothing else: it is never written to user_settings, never joined to a
 * historical pick, and never leaves the browser. picks.kelly_stake_fraction
 * is the only stake figure the system persists, and it is a percentage.
 */
const STORAGE_KEY = "night-ledger.display-bankroll";

interface BankrollState {
  bankroll: number | null;
  setBankroll: (value: number | null) => void;
  /** False until localStorage has been read, so the server and client agree. */
  ready: boolean;
}

const BankrollContext = createContext<BankrollState>({
  bankroll: null,
  setBankroll: () => undefined,
  ready: false,
});

export function BankrollProvider({ children }: { children: React.ReactNode }) {
  const [bankroll, setBankrollState] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      const parsed = raw === null ? NaN : Number(raw);
      if (Number.isFinite(parsed) && parsed > 0) setBankrollState(parsed);
    } catch {
      // Private-mode or blocked storage: the app works without it.
    }
    setReady(true);
  }, []);

  const value = useMemo<BankrollState>(
    () => ({
      bankroll,
      ready,
      setBankroll: (next) => {
        setBankrollState(next);
        try {
          if (next === null) window.localStorage.removeItem(STORAGE_KEY);
          else window.localStorage.setItem(STORAGE_KEY, String(next));
        } catch {
          // Non-fatal; the value still applies for this session.
        }
      },
    }),
    [bankroll, ready],
  );

  return (
    <BankrollContext.Provider value={value}>{children}</BankrollContext.Provider>
  );
}

export const useBankroll = () => useContext(BankrollContext);
