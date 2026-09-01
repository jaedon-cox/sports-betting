/**
 * The slate date is an ET calendar date set by the pipeline (see
 * db/views/v_todays_picks.sql), so every "today" question the frontend asks
 * must be asked in America/New_York — comparing against the server's UTC date
 * misaligns around midnight, which is precisely when a slate rolls over.
 */

const ET = "America/New_York";

const isoDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: ET,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const clock = new Intl.DateTimeFormat("en-US", {
  timeZone: ET,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const dayLabel = new Intl.DateTimeFormat("en-US", {
  timeZone: ET,
  weekday: "short",
  month: "short",
  day: "numeric",
});

/** "2026-08-31" in ET — the same key the pipeline writes to picks.game_date. */
export function etDate(at: Date = new Date()): string {
  return isoDate.format(at);
}

/** "7:05 PM" in ET. */
export function etClock(iso: string | null): string {
  if (!iso) return "—";
  return clock.format(new Date(iso));
}

/** "Sun, Aug 31" in ET. */
export function etDayLabel(iso: string): string {
  // A bare DATE has no zone; anchor it at noon UTC so ET formatting cannot
  // roll it back a day.
  const at = iso.length === 10 ? new Date(`${iso}T12:00:00Z`) : new Date(iso);
  return dayLabel.format(at);
}

/** "7:05 PM ET" — the banner's publish time. */
export function etStamp(iso: string | null): string {
  if (!iso) return "—";
  return `${clock.format(new Date(iso))} ET`;
}

/** Subtracts whole days from an ET slate date, returning the same string form. */
export function etDateMinusDays(days: number, from: Date = new Date()): string {
  const at = new Date(from.getTime() - days * 86_400_000);
  return etDate(at);
}
