import type { FC } from "react";
import { InsightBullet, type InsightTone } from "../ui/InsightBullet";
import type { TechnicalsDoc, SnapshotDoc } from "../../types";

type Insight = { tone: InsightTone; text: string };

// Derived, deterministic insights from technicals + latest snapshot. Only
// bullets whose underlying data is present render — nothing is invented.
function buildInsights(
  technicals: TechnicalsDoc | null | undefined,
  snapshot: SnapshotDoc | null | undefined,
  currentPrice: number | null,
): Insight[] {
  const out: Insight[] = [];

  if (technicals?.rsi_14 != null) {
    const rsi = technicals.rsi_14;
    if (rsi < 30) {
      out.push({ tone: "good", text: `RSI at ${rsi.toFixed(0)} — oversold zone, potential buying opportunity` });
    } else if (rsi > 70) {
      out.push({ tone: "warn", text: `RSI at ${rsi.toFixed(0)} — overbought, watch for pullback` });
    } else {
      out.push({ tone: "neutral", text: `RSI at ${rsi.toFixed(0)} — neutral momentum` });
    }
  }

  if (technicals?.macd_hist != null) {
    const h = technicals.macd_hist;
    if (h > 0) {
      out.push({ tone: "good", text: `MACD histogram positive (${h.toFixed(2)}) — bullish momentum` });
    } else if (h < 0) {
      out.push({ tone: "warn", text: `MACD histogram negative (${h.toFixed(2)}) — bearish momentum` });
    }
  }

  if (currentPrice != null && technicals?.sma_200 != null) {
    const diff = ((currentPrice - technicals.sma_200) / technicals.sma_200) * 100;
    if (diff > 0) {
      out.push({
        tone: "good",
        text: `Price ${diff.toFixed(1)}% above 200-day SMA — long-term uptrend intact`,
      });
    } else {
      out.push({
        tone: "warn",
        text: `Price ${Math.abs(diff).toFixed(1)}% below 200-day SMA — long-term downtrend`,
      });
    }
  }

  if (technicals?.volatility_30d != null && technicals.volatility_30d > 5) {
    out.push({
      tone: "warn",
      text: `30-day volatility ${technicals.volatility_30d.toFixed(1)}% — elevated risk`,
    });
  }

  // Prepend the model's own signal reasons when available — these come from
  // the pipeline and are already vetted against ensemble output.
  if (snapshot?.signal_reasons?.length) {
    const modelTone: InsightTone =
      snapshot.risk_adjusted_signal === "BUY"
        ? "good"
        : snapshot.risk_adjusted_signal === "SELL"
        ? "warn"
        : "neutral";
    for (const reason of snapshot.signal_reasons.slice(0, 2)) {
      out.unshift({ tone: modelTone, text: reason });
    }
  }

  return out.slice(0, 6);
}

type AIInsightsPanelProps = {
  technicals: TechnicalsDoc | null | undefined;
  snapshot: SnapshotDoc | null | undefined;
  currentPrice: number | null;
};

export const AIInsightsPanel: FC<AIInsightsPanelProps> = ({ technicals, snapshot, currentPrice }) => {
  const insights = buildInsights(technicals, snapshot, currentPrice);

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">AI Insights</h3>
        {snapshot?.risk_adjusted_signal && (
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
              snapshot.risk_adjusted_signal === "BUY"
                ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-500"
                : snapshot.risk_adjusted_signal === "SELL"
                ? "border-red-500/50 bg-red-500/10 text-red-500"
                : "border-amber-500/50 bg-amber-500/10 text-amber-500"
            }`}
          >
            {snapshot.risk_adjusted_signal}
          </span>
        )}
      </div>
      {insights.length === 0 ? (
        <p className="py-4 text-center text-xs text-hint">
          Not enough technical data to derive insights yet.
        </p>
      ) : (
        <ul className="divide-y divide-seam/40">
          {insights.map((ins, i) => (
            <InsightBullet key={i} tone={ins.tone}>
              {ins.text}
            </InsightBullet>
          ))}
        </ul>
      )}
    </div>
  );
};
