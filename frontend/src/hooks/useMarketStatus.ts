import { useEffect, useState } from "react";
import holidaysDoc from "../data/nse-holidays.json";

// NSE Kenya trading hours: Mon–Fri, 09:00–15:00 East Africa Time (UTC+3),
// closed on the holidays listed in nse-holidays.json. The audit flagged
// the chart badge saying "Market open" on a Saturday and the Home page
// saying "Live · 18:45 EAT" outside session hours — one hook now drives
// every "Market open" / "Live" / "Closed" badge across the app so those
// stay consistent.
//
// EAT is UTC+3 with no DST, so shifting the current time by the browser's
// timezone offset + 3h gives us the EAT wall-clock without needing a
// full tz library. Doing the math on numeric hours/minutes avoids
// Intl.DateTimeFormat locale surprises.

const OPEN_HOUR = 9;   // 09:00 EAT
const CLOSE_HOUR = 15; // 15:00 EAT

const HOLIDAYS: Set<string> = new Set(
  Array.isArray(holidaysDoc.holidays) ? holidaysDoc.holidays : []
);

export type MarketStatus =
  | { open: true;  reason: "open"; nowIso: string }
  | { open: false; reason: "weekend" | "holiday" | "pre-open" | "post-close"; nowIso: string; lastCloseIso: string };

function nowInEAT(): Date {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60_000;
  return new Date(utcMs + 3 * 60 * 60_000);
}

function isoDay(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Walk backwards day-by-day from today until we find a weekday that
// isn't a listed holiday. Used to render "last close YYYY-MM-DD" on
// closed states so the reader has a concrete anchor.
function lastTradingDay(now: Date): string {
  const cursor = new Date(now);
  for (let i = 0; i < 14; i += 1) {
    const dow = cursor.getUTCDay(); // 0 = Sun, 6 = Sat
    const iso = isoDay(cursor);
    if (dow !== 0 && dow !== 6 && !HOLIDAYS.has(iso)) return iso;
    cursor.setUTCDate(cursor.getUTCDate() - 1);
  }
  return isoDay(now);
}

export function computeStatus(): MarketStatus {
  const eat = nowInEAT();
  const dow = eat.getUTCDay();
  const iso = isoDay(eat);
  const hh = eat.getUTCHours();
  const mm = eat.getUTCMinutes();

  // Weekend
  if (dow === 0 || dow === 6) {
    return { open: false, reason: "weekend", nowIso: iso, lastCloseIso: lastTradingDay(eat) };
  }
  // Holiday
  if (HOLIDAYS.has(iso)) {
    return { open: false, reason: "holiday", nowIso: iso, lastCloseIso: lastTradingDay(eat) };
  }
  // Before session
  if (hh < OPEN_HOUR) {
    return { open: false, reason: "pre-open", nowIso: iso, lastCloseIso: lastTradingDay(eat) };
  }
  // After session (>= 15:00)
  if (hh > CLOSE_HOUR || (hh === CLOSE_HOUR && mm > 0)) {
    return { open: false, reason: "post-close", nowIso: iso, lastCloseIso: lastTradingDay(eat) };
  }
  return { open: true, reason: "open", nowIso: iso };
}

// React hook — recomputes once a minute so the badge flips at 09:00 and
// 15:00 without a page reload. Safe for SSR: initial state is computed
// eagerly but the interval only starts client-side.
export function useMarketStatus(): MarketStatus {
  const [status, setStatus] = useState<MarketStatus>(() => computeStatus());
  useEffect(() => {
    const tick = () => setStatus(computeStatus());
    tick();
    const id = window.setInterval(tick, 60_000);
    return () => window.clearInterval(id);
  }, []);
  return status;
}

// Convenience label for badges: "Market open" / "Market closed · last close 25 Sep 2026"
export function marketStatusLabel(s: MarketStatus): string {
  if (s.open) return "Market open";
  const d = new Date(`${s.lastCloseIso}T00:00:00Z`);
  const label = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  return `Market closed · last close ${label}`;
}
