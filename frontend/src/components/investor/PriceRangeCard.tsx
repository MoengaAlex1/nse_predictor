import type { FC } from "react";
import { RangeSlider } from "./RangeSlider";
import { resolveDisplayPrice } from "../../lib/format";
import type { CompanyDoc } from "../../types";
import type { RtdbPricePoint } from "../../hooks/useHistoricalPrices";

interface Props {
  company: CompanyDoc;
  /** Latest RTDB point for today's session — l/h/c/o feed the Day Range. */
  latest?: RtdbPricePoint | null;
  /** Optional pre-resolved display price from the parent's resolveDisplayPrice.
   *  Pass it when the parent already computed the resolver output so we don't
   *  re-run it; if omitted we resolve internally from (company, latest). */
  displayPrice?: number | null;
}

/**
 * Standalone sidebar card that shows two horizontal ranges — today's low→high
 * with the current close plotted on it, and the trailing-365-day low→high
 * with the same close plotted on it. Modelled directly on MSN Money's
 * "Day Range" and "52 Week Range" sliders.
 *
 * The price plotted on both sliders comes from the shared `resolveDisplayPrice`
 * helper so it can never disagree with the header, banner, or quote panel.
 */
export const PriceRangeCard: FC<Props> = ({ company, latest, displayPrice }) => {
  const currentPrice: number | null =
    displayPrice ?? resolveDisplayPrice(company, latest ?? null).price;

  // ── Day Range (from RTDB's latest bar) ────────────────────────────────
  const dayLow  = latest?.l  ?? null;
  const dayHigh = latest?.h  ?? null;
  const dayOpen = latest?.o  ?? null;
  const dayDate = latest?.date;
  const hasDayRange =
    dayLow != null && dayHigh != null && dayHigh > dayLow;

  // ── 52-week range (trailing 365 days of price_history) ────────────────
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 365);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const yearPrices = (company.price_history ?? [])
    .filter((p) => p.date >= cutoffStr)
    .map((p) => p.price);
  const low52  = yearPrices.length > 0 ? Math.min(...yearPrices) : null;
  const high52 = yearPrices.length > 0 ? Math.max(...yearPrices) : null;
  const has52  = low52 != null && high52 != null && high52 > low52;

  // If neither range has data, don't render an empty card — the sidebar
  // already has other tiles that carry their own "no data" states.
  if (!hasDayRange && !has52) return null;

  return (
    <div className="rounded-xl border border-rim bg-surface px-4 py-3 space-y-4">
      {hasDayRange && (
        <RangeSlider
          label="Day Range"
          low={dayLow!}
          high={dayHigh!}
          current={currentPrice}
          marker={dayOpen != null ? { label: "Open", value: dayOpen } : null}
          rightMeta={dayDate}
        />
      )}
      {has52 && (
        <RangeSlider
          label="52-Week Range"
          low={low52!}
          high={high52!}
          current={currentPrice}
        />
      )}
    </div>
  );
};
