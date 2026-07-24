import type { FC } from "react";
import { getCompanyProfile } from "../../data/companyProfiles";
import type { CompanyDoc, FinancialsDoc, SnapshotDoc, TechnicalsDoc } from "../../types";

const fmtVol = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n.toLocaleString();

const fmtKES = (n: number) => `KES ${n.toFixed(2)}`;

const SECTOR_MEDIAN_PE: Record<string, number | null> = {
  Banking: 7.8,
  Insurance: 6.2,
  "Manufacturing and Allied": 11.4,
  "Telecommunication and Technology": 18.5,
  "Energy and Petroleum": 9.1,
  "Commercial and Services": 13.2,
  Agricultural: 14.1,
  Investment: 8.9,
  "Real Estate Investment Trust": 22.0,
  "Automobiles and Accessories": 10.5,
  "Construction and Allied": 9.8,
  "Exchange Traded Funds": null,
};

interface Props {
  company: CompanyDoc;
  technicals: TechnicalsDoc | null | undefined;
  financials: FinancialsDoc | null | undefined;
  snapshot: SnapshotDoc | null | undefined;
}

const MetricChip: FC<{ label: string; value: string; accent?: string }> = ({
  label,
  value,
  accent,
}) => (
  <div className="rounded-lg border border-seam bg-raised/60 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
    <p className={`mt-0.5 font-mono text-sm font-semibold ${accent ?? "text-ink"}`}>{value}</p>
  </div>
);

export const QuoteSummaryPanel: FC<Props> = ({ company, technicals, financials, snapshot }) => {
  if (company.current_price === null) return null;

  const price = company.current_price;
  const profile = getCompanyProfile(company.ticker);

  // 52W high/low from last 365 days of price_history
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 365);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const yearPrices = (company.price_history ?? [])
    .filter((p) => p.date >= cutoffStr)
    .map((p) => p.price);
  const high52 = yearPrices.length > 0 ? Math.max(...yearPrices) : null;
  const low52 = yearPrices.length > 0 ? Math.min(...yearPrices) : null;
  const rangePos =
    high52 !== null && low52 !== null && high52 !== low52
      ? Math.round(((price - low52) / (high52 - low52)) * 100)
      : null;

  // Fundamentals
  const latestAnnual = financials?.annual?.[0] ?? null;
  const pe = latestAnnual?.eps && latestAnnual.eps > 0 ? price / latestAnnual.eps : null;
  const pb = latestAnnual?.bvps && latestAnnual.bvps > 0 ? price / latestAnnual.bvps : null;
  const eps = latestAnnual?.eps ?? null;

  const latestDiv = financials?.dividends?.[0] ?? null;
  const divYield =
    latestDiv?.amount_kes && price > 0 ? (latestDiv.amount_kes / price) * 100 : null;
  const today = new Date().toISOString().slice(0, 10);
  const nextDiv =
    latestDiv?.payment_date && latestDiv.payment_date >= today ? latestDiv : null;

  const sharesMn = profile.shares_outstanding_mn;
  const mktCapBn = sharesMn ? (price * sharesMn * 1_000_000) / 1_000_000_000 : null;

  const sectorMedianPe = SECTOR_MEDIAN_PE[company.sector] ?? null;

  // ML consensus from snapshot model_breakdown
  const breakdown = snapshot?.model_breakdown;
  const models = breakdown ? Object.values(breakdown) : [];
  const buyCount = models.filter((m) => m.signal === "BUY").length;
  const holdCount = models.filter((m) => m.signal === "HOLD").length;
  const sellCount = models.filter((m) => m.signal === "SELL").length;
  const totalModels = models.length;
  const targetAvg =
    totalModels > 0 ? models.reduce((s, m) => s + m.price, 0) / totalModels : null;
  const upside = targetAvg ? ((targetAvg - price) / price) * 100 : null;
  const consensusFill = totalModels > 0 ? Math.round((buyCount / totalModels) * 100) : 0;
  const consensusColor =
    buyCount > holdCount + sellCount
      ? "bg-emerald-500"
      : holdCount > sellCount
        ? "bg-amber-400"
        : "bg-red-500";

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface px-5 py-4 space-y-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        Quote Summary
      </p>

      {/* 52W range slider */}
      {high52 !== null && low52 !== null && (
        <div className="space-y-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            52-Week Range
          </span>
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-sub">{fmtKES(low52)}</span>
            <div className="relative flex-1 h-1.5 rounded-full bg-raised">
              <div className="absolute inset-0 rounded-full bg-seam/40" />
              {rangePos !== null && (
                <div
                  className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-sky-400 bg-surface shadow"
                  style={{ left: `calc(${rangePos}% - 6px)` }}
                />
              )}
            </div>
            <span className="font-mono text-xs text-sub">{fmtKES(high52)}</span>
          </div>
          {rangePos !== null && (
            <p className="text-right text-[10px] text-hint">{rangePos}% of 52W range</p>
          )}
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {technicals && <MetricChip label="Volume" value={fmtVol(technicals.volume)} />}
        {technicals && (
          <MetricChip label="Avg Vol 30D" value={fmtVol(technicals.avg_volume_30d)} />
        )}
        {mktCapBn !== null && (
          <MetricChip label="Mkt Cap" value={`KES ${mktCapBn.toFixed(1)}B`} />
        )}
        {pe !== null && <MetricChip label="P/E" value={`${pe.toFixed(1)}×`} />}
        {pb !== null && <MetricChip label="P/Book" value={`${pb.toFixed(2)}×`} />}
        {eps !== null && <MetricChip label="EPS (TTM)" value={`KES ${eps.toFixed(2)}`} />}
        {divYield !== null && (
          <MetricChip
            label="Div Yield"
            value={`${divYield.toFixed(1)}%`}
            accent="text-emerald-400"
          />
        )}
        {nextDiv && (
          <MetricChip label="Next Div" value={`KES ${nextDiv.amount_kes.toFixed(2)}`} />
        )}
        {sectorMedianPe !== null && pe !== null && (
          <MetricChip
            label="Sector P/E"
            value={`${sectorMedianPe.toFixed(1)}×`}
            accent={pe < sectorMedianPe ? "text-emerald-400" : "text-sub"}
          />
        )}
      </div>

      {/* ML consensus bar */}
      {totalModels > 0 && (
        <div className="border-t border-seam/60 pt-3 space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            ML Model Consensus
          </p>
          <div className="h-2 w-full overflow-hidden rounded-full bg-raised">
            <div
              className={`h-full rounded-full transition-all ${consensusColor}`}
              style={{ width: `${consensusFill}%` }}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span>
              {buyCount > 0 && (
                <span className="text-emerald-400 font-semibold">BUY {buyCount}</span>
              )}
              {holdCount > 0 && (
                <span className="ml-2 text-amber-400 font-semibold">HOLD {holdCount}</span>
              )}
              {sellCount > 0 && (
                <span className="ml-2 text-red-400 font-semibold">SELL {sellCount}</span>
              )}
            </span>
            {targetAvg !== null && upside !== null && (
              <span className="font-mono text-sub">
                Target {fmtKES(targetAvg)}
                <span className={upside >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {" "}
                  ({upside >= 0 ? "+" : ""}
                  {upside.toFixed(1)}%)
                </span>
              </span>
            )}
          </div>
          {breakdown && (
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[10px] text-hint">
              {Object.entries(breakdown).map(([model, d]) => (
                <span key={model}>
                  {model}:{" "}
                  <span
                    className={
                      d.signal === "BUY"
                        ? "text-emerald-400"
                        : d.signal === "SELL"
                          ? "text-red-400"
                          : "text-amber-400"
                    }
                  >
                    {d.signal}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
