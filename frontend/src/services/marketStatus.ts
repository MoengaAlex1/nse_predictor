/**
 * NSE trading session status in East Africa Time (phase 1 task 3).
 *
 * The NSE trades 09:00–15:00 EAT, Monday to Friday. EAT is UTC+3 year round
 * with no daylight saving, so the offset is a constant rather than a lookup.
 * Public holidays are not modelled — a holiday reads as OPEN here, which is
 * why the pill says "scheduled" rather than asserting live trading.
 */
export const EAT_OFFSET_HOURS = 3;
export const OPEN_HOUR_EAT = 9;
export const CLOSE_HOUR_EAT = 15;

export interface MarketStatus {
  isOpen: boolean;
  /** Local EAT time as HH:MM. */
  nowEat: string;
  /** When the next session opens, e.g. "Mon 09:00". Null while open. */
  nextOpen: string | null;
}

/** Shift a UTC instant into EAT and read its calendar parts. */
function eatParts(now: Date) {
  const eat = new Date(now.getTime() + EAT_OFFSET_HOURS * 3600_000);
  return {
    day: eat.getUTCDay(),        // 0 Sun .. 6 Sat
    hour: eat.getUTCHours(),
    minute: eat.getUTCMinutes(),
  };
}

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function marketStatus(now: Date = new Date()): MarketStatus {
  const { day, hour, minute } = eatParts(now);
  const isWeekday = day >= 1 && day <= 5;
  const isOpen = isWeekday && hour >= OPEN_HOUR_EAT && hour < CLOSE_HOUR_EAT;
  const nowEat = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

  if (isOpen) return { isOpen, nowEat, nextOpen: null };

  // Walk forward to the next weekday session that has not already started.
  let addDays = 0;
  if (isWeekday && hour < OPEN_HOUR_EAT) {
    addDays = 0;                       // opens later today
  } else {
    addDays = 1;
    while (((day + addDays) % 7) === 0 || ((day + addDays) % 7) === 6) addDays++;
  }
  const nextDay = DAY_NAMES[(day + addDays) % 7];
  const label = addDays === 0 ? "today" : nextDay;
  return {
    isOpen,
    nowEat,
    nextOpen: `${label} ${String(OPEN_HOUR_EAT).padStart(2, "0")}:00`,
  };
}
