import type { FC } from "react";
import { fmtLabel } from "../../lib/dateUtils";

interface Props {
  /** Latest known price in KES — RTDB close, live current, or last EOD. */
  currentPrice: number | null;
  /** Previous session close in KES, used to frame the move. */
  previousClose: number | null;
  /** Signed change % vs previous close (e.g. -1.97 for a 1.97% drop). */
  changePct: number | null;
  /** ISO date the price is dated against (YYYY-MM-DD or ISO timestamp). */
  priceDate: string | null;
}

const fmtPct = (v: number): string => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
const fmtKES = (v: number): string => `KES ${v.toFixed(2)}`;

/**
 * MSN Money-style price-move alert banner.
 *
 * On MSN's INTC page a full-width sky/red band above the header reads
 * "▼ Price down: -1.97% from the previous close price of $104.56 as of
 * August 14 04:00 PM EDT". The value it adds over the small delta chip in
 * the header is framing — a reader lands on the page and already knows the
 * direction, the magnitude, and what it's a move FROM, without having to
 * find and interpret the coloured chip.
 *
 * We only render when a change % and a current price are both available.
 * When either is missing (SCOM today has current_price = null on the
 * CompanyDoc even though the RTDB has today's bar) the banner returns null
 * rather than filling with dashes — the caller is expected to fall through
 * the price tiers before passing values in.
 */
export const PriceMoveBanner: FC<Props> = ({
  currentPrice, previousClose, changePct, priceDate,
}) => {
  if (changePct == null || currentPrice == null) return null;

  const isUp = changePct >= 0;
  const arrow = isUp ? "▲" : "▼";
  const wording = isUp ? "Price up" : "Price down";
  const tone = isUp
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
    : "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400";

  const prevPart = previousClose != null
    ? ` from the previous close of ${fmtKES(previousClose)}`
    : "";
  const datePart = priceDate ? ` as of ${fmtLabel(priceDate)}` : "";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold ${tone}`}
    >
      <span aria-hidden="true" className="font-mono">{arrow}</span>
      <span>
        {wording} <span className="font-mono">{fmtPct(changePct)}</span>
        {prevPart}
        {datePart && <span className="font-normal opacity-80">{datePart}</span>}
      </span>
    </div>
  );
};
