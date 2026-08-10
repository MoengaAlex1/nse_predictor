import type { FC } from "react";
import { StatRow } from "../ui/StatRow";
import { MiniRangeBar } from "../ui/MiniRangeBar";
import type { CompanyDoc, TechnicalsDoc, FundamentalsDoc } from "../../types";

type RightStatsRailProps = {
  company: CompanyDoc | null | undefined;
  technicals: TechnicalsDoc | null | undefined;
  fundamentals: FundamentalsDoc | null | undefined;
  dayLow: number | null;
  dayHigh: number | null;
  previousClose: number | null;
};

const fmtVolume = (v: number | null | undefined): string => {
  if (v == null) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString();
};

const fmtKes = (v: number | null | undefined): string => {
  if (v == null) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  return v.toFixed(2);
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

  // Market cap = current price × shares outstanding, only when both are known
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
            <span className="font-mono text-[10px] text-hint">
              {dayLow.toFixed(2)} – {dayHigh.toFixed(2)}
            </span>
          )}
        </div>
        <MiniRangeBar low={dayLow} high={dayHigh} current={currentPrice} />
      </div>

      <div>
        <StatRow
          label="Previous Close"
          value={previousClose != null ? previousClose.toFixed(2) : undefined}
          placeholder={previousClose == null}
        />
        <StatRow
          label="Average Volume"
          value={fmtVolume(technicals?.avg_volume_30d)}
          placeholder={technicals?.avg_volume_30d == null}
        />
        <StatRow
          label="Market Cap"
          value={marketCap != null ? `KES ${fmtKes(marketCap)}` : undefined}
          placeholder={marketCap == null}
          hint="Current price × shares outstanding"
        />
        <StatRow
          label="Shares Outstanding"
          value={sharesOutstanding != null ? fmtKes(sharesOutstanding) : undefined}
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
