import type { FC } from "react";
import { StatRow } from "../ui/StatRow";
import { MiniRangeBar } from "../ui/MiniRangeBar";
import { fmtCompact, fmtCompactKes, fmtPrice } from "../../lib/format";
import type { CompanyDoc, TechnicalsDoc, FundamentalsDoc, FinancialsDoc } from "../../types";

type RightStatsRailProps = {
  company: CompanyDoc | null | undefined;
  technicals: TechnicalsDoc | null | undefined;
  fundamentals: FundamentalsDoc | null | undefined;
  financials: FinancialsDoc | null | undefined;
  dayLow: number | null;
  dayHigh: number | null;
  previousClose: number | null;
};

// Trailing 12-month EPS = most recent annual result's EPS. NSE reporters
// publish annual results once a year, so this is the natural TTM value
// available without an interim-stitching pipeline.
function ttmEps(financials: FinancialsDoc | null | undefined): number | null {
  if (!financials?.annual?.length) return null;
  const sorted = [...financials.annual].sort((a, b) => b.period_end.localeCompare(a.period_end));
  return sorted[0]?.eps ?? null;
}

// Dividend yield (TTM) = sum of dividend amounts announced in the last 365
// days / current price. Uses announcement_date since ex/payment can be
// missing on older records. Returns null if no dividends in-window.
function ttmDividendYield(
  financials: FinancialsDoc | null | undefined,
  price: number | null,
): number | null {
  if (!financials?.dividends?.length || price == null || price <= 0) return null;
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - 1);
  const cutIso = cutoff.toISOString().slice(0, 10);
  const total = financials.dividends
    .filter((d) => d.announcement_date >= cutIso && d.type !== "none")
    .reduce((sum, d) => sum + (d.amount_kes ?? 0), 0);
  if (total <= 0) return null;
  return (total / price) * 100;
}

function lastExDivDate(financials: FinancialsDoc | null | undefined): string | null {
  if (!financials?.dividends?.length) return null;
  const withEx = financials.dividends
    .filter((d) => d.ex_date && d.type !== "none")
    .sort((a, b) => (b.ex_date ?? "").localeCompare(a.ex_date ?? ""));
  return withEx[0]?.ex_date ?? null;
}

export const RightStatsRail: FC<RightStatsRailProps> = ({
  company,
  technicals,
  fundamentals,
  financials,
  dayLow,
  dayHigh,
  previousClose,
}) => {
  const currentPrice = company?.current_price ?? null;

  const sharesOutstanding =
    fundamentals?.shares_outstanding_mn != null ? fundamentals.shares_outstanding_mn * 1_000_000 : null;

  const marketCap =
    currentPrice != null && sharesOutstanding != null ? currentPrice * sharesOutstanding : null;

  const eps = ttmEps(financials);
  const pe = currentPrice != null && eps != null && eps > 0 ? currentPrice / eps : null;
  const divYield = ttmDividendYield(financials, currentPrice);
  const exDivDate = lastExDivDate(financials);

  return (
    <aside className="flex flex-col gap-4 rounded-xl border border-rim bg-surface p-4">
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Day Range
          </span>
          {dayLow != null && dayHigh != null && (
            <span className="font-mono text-[10px] tabular-nums text-hint">
              {fmtPrice(dayLow)} – {fmtPrice(dayHigh)}
            </span>
          )}
        </div>
        <MiniRangeBar low={dayLow} high={dayHigh} current={currentPrice} />
      </div>

      <div>
        <StatRow
          label="Previous Close"
          value={fmtPrice(previousClose)}
          placeholder={previousClose == null}
        />
        <StatRow
          label="Average Volume"
          value={fmtCompact(technicals?.avg_volume_30d)}
          placeholder={technicals?.avg_volume_30d == null}
          hint="30-day trailing average"
        />
        <StatRow
          label="Market Cap"
          value={fmtCompactKes(marketCap)}
          placeholder={marketCap == null}
          hint="Current price × shares outstanding"
        />
        <StatRow
          label="Shares Outstanding"
          value={fmtCompact(sharesOutstanding)}
          placeholder={sharesOutstanding == null}
        />
        <StatRow
          label="EPS (TTM)"
          value={eps != null ? fmtPrice(eps) : undefined}
          placeholder={eps == null}
          hint="Latest annual result — trailing 12 months"
        />
        <StatRow
          label="P/E (TTM)"
          value={pe != null ? `${pe.toFixed(1)}×` : undefined}
          placeholder={pe == null}
          hint="Current price ÷ EPS (TTM)"
        />
        <StatRow
          label="Dividend Yield (TTM)"
          value={divYield != null ? `${divYield.toFixed(2)}%` : undefined}
          placeholder={divYield == null}
          hint="Sum of dividends in the last 365 days ÷ current price"
        />
        <StatRow
          label="Last Ex-Div Date"
          value={exDivDate ?? undefined}
          placeholder={exDivDate == null}
          hint="Ex-date of the most recent dividend"
        />
      </div>
    </aside>
  );
};
