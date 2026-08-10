import type { FC } from "react";
import { StatRow } from "../ui/StatRow";
import { MiniRangeBar } from "../ui/MiniRangeBar";
import { fmtCompact, fmtCompactKes, fmtPrice } from "../../lib/format";
import type { CompanyDoc, TechnicalsDoc, FundamentalsDoc } from "../../types";

type RightStatsRailProps = {
  company: CompanyDoc | null | undefined;
  technicals: TechnicalsDoc | null | undefined;
  fundamentals: FundamentalsDoc | null | undefined;
  dayLow: number | null;
  dayHigh: number | null;
  previousClose: number | null;
};

export const RightStatsRail: FC<RightStatsRailProps> = ({
  company,
  technicals,
  fundamentals,
  dayLow,
  dayHigh,
  previousClose,
}) => {
  const currentPrice = company?.current_price ?? null;

  const sharesOutstanding =
    fundamentals?.shares_outstanding_mn != null ? fundamentals.shares_outstanding_mn * 1_000_000 : null;

  // Market cap = current price × shares outstanding, only when both are known.
  const marketCap =
    currentPrice != null && sharesOutstanding != null ? currentPrice * sharesOutstanding : null;

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
        <StatRow label="EPS (TTM)" placeholder hint="Coming soon" />
        <StatRow label="P/E (TTM)" placeholder hint="Coming soon" />
        <StatRow label="Fwd Dividend (% Yield)" placeholder hint="Coming soon" />
        <StatRow label="Ex-Dividend Date" placeholder hint="Coming soon" />
      </div>
    </aside>
  );
};
