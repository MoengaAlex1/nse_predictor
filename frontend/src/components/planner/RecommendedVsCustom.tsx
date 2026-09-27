import type { FC } from "react";
import type { PortfolioMetrics } from "../../lib/portfolio";
import { fmtKes, fmtPct } from "../../lib/format";

// Phase 3 — side-by-side metric compare. No "better/worse" labels
// (per the spec) — just the numbers and the delta so the user sees
// the consequence of their edits.

interface Props {
  amountKes: number;
  recommended: PortfolioMetrics | null;
  custom: PortfolioMetrics | null;
}

interface Row {
  label: string;
  format: (m: PortfolioMetrics) => string;
  delta?: (rec: PortfolioMetrics, cus: PortfolioMetrics) => { value: string; tone: "up" | "down" | "neutral" };
}

export const RecommendedVsCustom: FC<Props> = ({ amountKes, recommended, custom }) => {
  if (!recommended || !custom) return null;

  const rows: Row[] = [
    {
      label: "Expected value",
      format: (m) => fmtKes(m.expectedValueKes),
      delta: (r, c) => absDelta(c.expectedValueKes - r.expectedValueKes),
    },
    {
      label: "Expected return",
      format: (m) => fmtPct(m.expectedReturnPct),
      delta: (r, c) => absDelta(c.expectedReturnPct - r.expectedReturnPct, "%"),
    },
    {
      label: "Conservative band",
      format: (m) => fmtKes(m.conservativeValueKes),
    },
    {
      label: "Optimistic band",
      format: (m) => fmtKes(m.optimisticValueKes),
    },
    {
      label: "Portfolio volatility (σ)",
      format: (m) => `${m.portfolioSigmaPct.toFixed(2)}% at horizon`,
      // Higher volatility isn't good or bad; label neutral.
      delta: (r, c) => absDelta(c.portfolioSigmaPct - r.portfolioSigmaPct, "%", "neutral"),
    },
    {
      label: "Risk band",
      format: (m) => m.riskBand,
    },
    {
      label: "Diversification",
      format: (m) => `${m.diversification.score} · ${m.diversification.sectorCount} sectors`,
    },
    {
      label: "Concentration (HHI)",
      format: (m) => m.diversification.hhi.toFixed(3),
      // Lower HHI = more diverse. Neg delta = more diverse (up), pos = more concentrated (down).
      delta: (r, c) => {
        const d = c.diversification.hhi - r.diversification.hhi;
        return { value: (d >= 0 ? "+" : "") + d.toFixed(3), tone: d < 0 ? "up" : d > 0 ? "down" : "neutral" };
      },
    },
    {
      label: "Avg pairwise correlation",
      format: (m) => m.diversification.avgPairwiseCorr != null
        ? m.diversification.avgPairwiseCorr.toFixed(2)
        : "—",
      // Lower correlation = better diversification benefit.
      delta: (r, c) => {
        if (r.diversification.avgPairwiseCorr == null || c.diversification.avgPairwiseCorr == null) return { value: "—", tone: "neutral" };
        const d = c.diversification.avgPairwiseCorr - r.diversification.avgPairwiseCorr;
        return { value: (d >= 0 ? "+" : "") + d.toFixed(2), tone: d < 0 ? "up" : d > 0 ? "down" : "neutral" };
      },
    },
  ];

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">Recommended vs your custom</h2>
        <p className="text-[11px] text-hint">Investment {fmtKes(amountKes)}. Deltas are Custom − Recommended.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-seam text-[10px] uppercase tracking-wider text-muted">
              <th className="py-2 pr-3 text-left">Metric</th>
              <th className="py-2 pr-3 text-right">Recommended</th>
              <th className="py-2 pr-3 text-right">Your custom</th>
              <th className="py-2 pl-3 text-right">Δ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-seam/50">
            {rows.map(r => {
              const dObj = r.delta ? r.delta(recommended, custom) : null;
              const dCls = dObj?.tone === "up"
                ? "text-emerald-600 dark:text-emerald-400"
                : dObj?.tone === "down"
                  ? "text-red-600 dark:text-red-400"
                  : "text-muted";
              return (
                <tr key={r.label} className="hover:bg-raised/30">
                  <td className="py-2 pr-3 text-sub">{r.label}</td>
                  <td className="py-2 pr-3 text-right font-mono tabular-nums text-ink">{r.format(recommended)}</td>
                  <td className="py-2 pr-3 text-right font-mono tabular-nums text-ink">{r.format(custom)}</td>
                  <td className={`py-2 pl-3 text-right font-mono tabular-nums ${dCls}`}>
                    {dObj?.value ?? ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-hint">
        Δ colouring: green = improvement for that metric (higher expected value, lower
        volatility, more diverse), red = the opposite. Neutral where the metric doesn't
        have a natural directional preference.
      </p>
    </div>
  );
};

function absDelta(v: number, suffix = "", forceTone?: "up" | "down" | "neutral"): { value: string; tone: "up" | "down" | "neutral" } {
  const sign = v >= 0 ? "+" : "";
  const value = suffix === "%"
    ? `${sign}${v.toFixed(2)}%`
    : `${sign}${fmtKes(v, { prefix: false })}`;
  const tone: "up" | "down" | "neutral" = forceTone ?? (v > 0 ? "up" : v < 0 ? "down" : "neutral");
  return { value, tone };
}
