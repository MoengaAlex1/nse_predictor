import { useState } from "react";
import { useFinancialAnalysis } from "../hooks/useFinancialAnalysis";

type NarrativeKey = "revenue_trend" | "profit_trend" | "debt_levels" | "cash_flow_health" | "dividend_history";

const sections: { key: NarrativeKey; label: string }[] = [
  { key: "revenue_trend",    label: "Revenue" },
  { key: "profit_trend",     label: "Profit" },
  { key: "debt_levels",      label: "Debt" },
  { key: "cash_flow_health", label: "Cash Flow" },
  { key: "dividend_history", label: "Dividends" },
];

export function FinancialNarrativeCard({ ticker }: { ticker: string }) {
  const { data, isLoading, isError } = useFinancialAnalysis(ticker);
  const [expanded, setExpanded] = useState<NarrativeKey | null>(null);

  if (isLoading) return null;
  if (isError) return <div className="text-red-500 text-sm p-4">Failed to load analysis.</div>;
  if (!data) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 mt-3">
      <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">{data.summary}</p>

      <div className="flex gap-2 flex-wrap mb-4">
        {sections.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setExpanded(expanded === key ? null : key)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              expanded === key
                ? "bg-blue-600 text-white"
                : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {expanded && (
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          {data[expanded]}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 mt-2">
        <div>
          <p className="text-xs font-semibold text-red-500 mb-1">Key Risks</p>
          <ul className="space-y-1">
            {data.key_risks.map((r, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-gray-400 flex gap-1">
                <span className="text-red-400 mt-0.5">•</span>{r}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold text-green-500 mb-1">Growth Opportunities</p>
          <ul className="space-y-1">
            {data.growth_opportunities.map((o, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-gray-400 flex gap-1">
                <span className="text-green-400 mt-0.5">•</span>{o}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="text-xs text-gray-400 mt-3">
        Analysis generated {new Date(data.generated_at).toLocaleDateString()}
      </p>
    </div>
  );
}
