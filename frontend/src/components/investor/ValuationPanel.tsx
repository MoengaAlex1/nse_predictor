import { useState } from "react";
import type { FC } from "react";
import type { CompanyDoc, FinancialsDoc, FundamentalsDoc, FinancialResult } from "../../types";
import { getCompanyProfile } from "../../data/companyProfiles";

type Tab = "valuation" | "income" | "dividends";

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

const fmt = (v: number | null, suffix = "", decimals = 2) =>
  v !== null ? `${v.toFixed(decimals)}${suffix}` : "—";

const TabBtn: FC<{ label: string; active: boolean; onClick: () => void }> = ({ label, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded px-3 py-1 text-xs font-semibold transition-colors ${
      active ? "bg-sky-600 text-white" : "text-muted hover:bg-rim hover:text-sub"
    }`}
  >
    {label}
  </button>
);

interface Props {
  company: CompanyDoc;
  financials: FinancialsDoc | null | undefined;
  fundamentals: FundamentalsDoc | null | undefined;
}

export const ValuationPanel: FC<Props> = ({ company, financials, fundamentals }) => {
  const [tab, setTab] = useState<Tab>("valuation");

  if (!financials?.annual?.length) return null;

  const price = company.current_price ?? 0;
  const profile = getCompanyProfile(company.ticker);
  const sharesMn = fundamentals?.shares_outstanding_mn ?? profile.shares_outstanding_mn;

  const annuals = [...financials.annual]
    .sort((a, b) => b.period_end.localeCompare(a.period_end))
    .slice(0, 3);

  const estimates = fundamentals?.estimates ?? [];
  const forwardPeriod = estimates[0]?.period ?? null;

  const sectorMedianPE = SECTOR_MEDIAN_PE[company.sector] ?? null;
  const currentPE = annuals[0]?.eps && annuals[0].eps > 0 ? price / annuals[0].eps : null;
  const sectorDiff =
    currentPE && sectorMedianPE
      ? ((currentPE - sectorMedianPE) / sectorMedianPE) * 100
      : null;

  const computeROE = (row: FinancialResult) => {
    if (!row.net_income_kes_mn || !row.bvps || !sharesMn) return null;
    const equity = row.bvps * sharesMn * 1_000_000;
    if (equity <= 0) return null;
    return (row.net_income_kes_mn * 1_000_000 / equity) * 100;
  };

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam/60 px-5 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Company Valuation</p>
        <div className="flex gap-1">
          <TabBtn label="Valuation" active={tab === "valuation"} onClick={() => setTab("valuation")} />
          <TabBtn label="Income"    active={tab === "income"}    onClick={() => setTab("income")} />
          <TabBtn label="Dividends" active={tab === "dividends"} onClick={() => setTab("dividends")} />
        </div>
      </div>

      <div className="px-5 py-4">
        {tab === "valuation" && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-raised/60">
                    <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Metric</th>
                    {annuals.map((r) => (
                      <th key={r.period} className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">
                        {r.period}
                      </th>
                    ))}
                    {forwardPeriod && (
                      <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-sky-600/70">
                        {forwardPeriod}
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-seam/50">
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">EPS (KES)</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(r.eps)}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-sky-500/80">{fmt(estimates[0]?.eps_kes ?? null)} <span className="text-[10px] text-hint">est.</span></td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">P/E Ratio</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.eps && r.eps > 0 ? `${(price / r.eps).toFixed(1)}×` : "—"}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-sky-500/80">{fmt(estimates[0]?.pe_forward ?? null, "×")} <span className="text-[10px] text-hint">est.</span></td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">BVPS (KES)</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(r.bvps)}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-hint">—</td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">P/Book</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.bvps && r.bvps > 0 ? `${(price / r.bvps).toFixed(2)}×` : "—"}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-hint">—</td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">ROE</td>
                    {annuals.map((r) => {
                      const roe = computeROE(r);
                      return <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(roe, "%", 1)}</td>;
                    })}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-hint">—</td>}
                  </tr>
                </tbody>
              </table>
            </div>

            {sectorMedianPE !== null && currentPE !== null && sectorDiff !== null && (
              <div className="mt-4 rounded-lg border border-seam/60 bg-raised/30 px-4 py-2.5">
                <p className="text-xs text-sub">
                  <span className="font-semibold text-muted uppercase tracking-wider text-[10px]">Sector Peer Snapshot · </span>
                  {company.sector} sector median P/E: <span className="font-mono font-semibold text-ink">{sectorMedianPE}×</span>
                  &emsp;
                  <span className={sectorDiff >= 0 ? "text-amber-400" : "text-emerald-400"}>
                    ({sectorDiff >= 0 ? "+" : ""}{sectorDiff.toFixed(0)}% vs sector)
                  </span>
                </p>
              </div>
            )}
          </>
        )}

        {tab === "income" && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-raised/60">
                  <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Metric</th>
                  {annuals.map((r) => (
                    <th key={r.period} className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">{r.period}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-seam/50">
                <tr className="hover:bg-raised/20 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-sub">Revenue (KES Mn)</td>
                  {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.revenue_kes_mn ? r.revenue_kes_mn.toLocaleString() : "—"}</td>)}
                </tr>
                <tr className="hover:bg-raised/20 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-sub">Net Income (KES Mn)</td>
                  {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.net_income_kes_mn ? r.net_income_kes_mn.toLocaleString() : "—"}</td>)}
                </tr>
                <tr className="hover:bg-raised/20 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-sub">EPS (KES)</td>
                  {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(r.eps)}</td>)}
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {tab === "dividends" && (
          <div className="overflow-x-auto">
            {financials.dividends.length === 0 ? (
              <p className="text-sm text-muted py-2">No dividend history on record.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-raised/60">
                    <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Type</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Amount (KES)</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Yield</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Ex-Date</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Payment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-seam/50">
                  {financials.dividends.slice(0, 8).map((d, i) => {
                    const amt = d.amount_kes;
                    const yld = amt != null && price > 0 ? ((amt / price) * 100).toFixed(1) : null;
                    return (
                      <tr key={i} className={`hover:bg-raised/20 transition-colors ${i === 0 ? "bg-emerald-950/10" : ""}`}>
                        <td className="px-3 py-2.5 font-medium text-sub capitalize">{d.type}</td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold text-emerald-400">{amt != null ? amt.toFixed(2) : "—"}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-sub">{yld ? `${yld}%` : "—"}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-hint">{d.ex_date ?? "—"}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-hint">{d.payment_date ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
