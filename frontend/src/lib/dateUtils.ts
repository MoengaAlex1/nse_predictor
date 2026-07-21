const LOCALE = "en-KE";

/** "Jan 15" */
export const fmtShort = (dateStr: string): string => {
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(LOCALE, { month: "short", day: "numeric" });
};

/** "Mon, Jan 15, 2024" */
export const fmtLabel = (dateStr: string): string => {
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(LOCALE, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

/** "Jan 15, 2024" */
export const fmtMedium = (dateStr: string): string => {
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(LOCALE, { year: "numeric", month: "short", day: "numeric" });
};

/** "Monday, January 15, 2024" */
export const fmtDate = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(LOCALE, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
};

/** "Mon, Jul 20" — weekday + short date without year, for compact price labels */
export const fmtDay = (dateStr: string): string => {
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(LOCALE, { weekday: "short", month: "short", day: "numeric" });
};

/** Advance/retreat `offset` trading days from a base Date; returns ISO date string. */
export const tradingDaysFrom = (base: Date, offset: number): string => {
  const d = new Date(base);
  let remaining = Math.abs(offset);
  const direction = offset >= 0 ? 1 : -1;
  while (remaining > 0) {
    d.setDate(d.getDate() + direction);
    const day = d.getDay();
    if (day !== 0 && day !== 6) remaining--;
  }
  return d.toISOString().slice(0, 10);
};
