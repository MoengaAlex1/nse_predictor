import type { FC } from "react";
import { useDeepAnalysis } from "../hooks/useDeepAnalysis";
import type { DeepEvent } from "../hooks/useDeepAnalysis";

const DRIVER_BADGE: Record<string, string> = {
  fundamental:      "bg-blue-900/50 text-blue-300 border-blue-800/50",
  sentiment:        "bg-amber-900/50 text-amber-300 border-amber-800/50",
  technical:        "bg-violet-900/50 text-violet-300 border-violet-800/50",
  corporate_action: "bg-emerald-900/50 text-emerald-300 border-emerald-800/50",
};

const DRIVER_LABEL: Record<string, string> = {
  fundamental:      "Fundamental",
  sentiment:        "Sentiment",
  technical:        "Technical",
  corporate_action: "Corp Action",
};

const ConfidenceDots: FC<{ score: number; max?: number }> = ({ score, max = 5 }) => (
  <div className="flex items-center gap-1" aria-label={`Confidence ${score} of ${max}`}>
    {Array.from({ length: max }, (_, i) => (
      <span
        key={i}
        className={`inline-block h-2 w-2 rounded-full ${
          i < score ? "bg-sky-400" : "bg-raised border border-seam"
        }`}
      />
    ))}
  </div>
);

const ImpactBadge: FC<{ impact: string }> = ({ impact }) => {
  const color = impact.startsWith("+")
    ? "bg-emerald-900/50 text-emerald-300 border-emerald-800/50"
    : impact.startsWith("-")
    ? "bg-red-900/50 text-red-300 border-red-800/50"
    : "bg-slate-700/60 text-slate-300 border-slate-600";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${color}`}>
      {impact}
    </span>
  );
};

export function DeepAnalysisPanel({ ticker }: { ticker: string }) {
  const { data, isLoading, isError } = useDeepAnalysis(ticker);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4 space-y-3 animate-pulse">
        <div className="h-4 w-48 rounded bg-raised" />
        <div className="h-3 w-full rounded bg-raised" />
        <div className="h-3 w-3/4 rounded bg-raised" />
      </div>
    );
  }

  if (isError) {
    return <div className="text-red-500 text-sm p-4">Failed to load analysis.</div>;
  }

  if (!data) {
    return <div className="text-gray-400 text-sm p-4">No analysis available yet.</div>;
  }

  const driverBadge = DRIVER_BADGE[data.driver_type] ?? "bg-slate-700/60 text-slate-300 border-slate-600";
  const driverLabel = DRIVER_LABEL[data.driver_type] ?? data.driver_type;

  const analysisDate = (() => {
    try {
      return new Date(data.generated_at).toISOString().slice(0, 10);
    } catch {
      return data.generated_at;
    }
  })();

  return (
    <div className="rounded-xl border border-rim bg-surface p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-sub">
          Price Movement Analysis
        </h2>
        <div className="flex items-center gap-2">
          <span className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${driverBadge}`}>
            {driverLabel}
          </span>
          <ConfidenceDots score={data.confidence} />
        </div>
      </div>

      {/* Explanation */}
      <p className="text-sm leading-relaxed text-sub">{data.price_movement_explanation}</p>

      {/* Key events */}
      {data.key_events.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Key Events
          </p>
          <ul className="space-y-1.5">
            {data.key_events.map((ev: DeepEvent) => (
              <li
                key={ev.date + ev.event}
                className="flex flex-wrap items-start gap-2 text-xs"
              >
                <span className="shrink-0 font-mono text-[10px] text-hint pt-0.5 w-20">
                  {ev.date}
                </span>
                <span className="flex-1 text-sub">{ev.event}</span>
                <ImpactBadge impact={ev.estimated_impact} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Outlook */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-seam bg-raised/60 p-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Short-term (2-4 weeks)
          </p>
          <p className="text-xs leading-relaxed text-sub">{data.outlook.short_term}</p>
        </div>
        <div className="rounded-lg border border-seam bg-raised/60 p-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Medium-term (3-6 months)
          </p>
          <p className="text-xs leading-relaxed text-sub">{data.outlook.medium_term}</p>
        </div>
      </div>

      {/* Footer */}
      <p className="text-[10px] font-mono text-hint">Analysis from {analysisDate}</p>
    </div>
  );
}
