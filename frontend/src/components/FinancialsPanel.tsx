import { useState } from "react";
import { useFinancials, type MetricValue } from "../hooks/useFinancials";

const TABS = ["Income Statement", "Cash Flow", "Balance Sheet", "Per Share"] as const;
type Tab = typeof TABS[number];

const SECTION_MAP: Record<Tab, string> = {
  "Income Statement": "income_statement",
  "Cash Flow":        "cash_flow",
  "Balance Sheet":    "balance_sheet",
  "Per Share":        "per_share",
};

const LABEL_MAP: Record<string, string> = {
  gross_revenue:                "Gross Revenue",
  excise_duty_and_vat:          "Excise Duty & VAT",
  net_revenue:                  "Net Revenue",
  cost_of_operations:           "Cost of Operations",
  operating_profit:             "Operating Profit",
  finance_income:               "Finance Income",
  profit_before_tax:            "Profit Before Tax",
  income_tax_expense:           "Income Tax Expense",
  profit_after_tax:             "Profit After Tax",
  basic_diluted_eps:            "Basic & Diluted EPS",
  interim_dividend_per_share:   "Interim Dividend Per Share",
  retained_earnings:            "Retained Earnings",
  shareholders_funds:           "Shareholders' Funds",
  net_cash_from_operations:     "Net Cash from Operations",
  net_cash_operating_activities: "Net Cash (Operating)",
  net_cash_investing_activities: "Net Cash (Investing)",
  net_cash_financing_activities: "Net Cash (Financing)",
  movement_in_cash:             "Movement in Cash",
  cash_at_period_end:           "Cash at Period End",
};

function YoyBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-gray-400">—</span>;
  const up = pct >= 0;
  return (
    <span className={`text-xs font-semibold ${up ? "text-green-500" : "text-red-500"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

function MetricRow({ label, metric }: { label: string; metric: MetricValue }) {
  const fmt = (v: number | null) =>
    v === null ? "—" : `${metric.currency} ${v.toLocaleString()} ${metric.unit}`;
  return (
    <tr className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
      <td className="py-2 pr-4 text-sm text-gray-700 dark:text-gray-300">{label}</td>
      <td className="py-2 pr-4 text-sm font-medium text-right">{fmt(metric.current)}</td>
      <td className="py-2 pr-4 text-sm text-gray-500 text-right">{fmt(metric.prior)}</td>
      <td className="py-2 text-right"><YoyBadge pct={metric.yoy_pct} /></td>
    </tr>
  );
}

export function FinancialsPanel({ ticker }: { ticker: string }) {
  const [tab, setTab] = useState<Tab>("Income Statement");
  const { data, isLoading } = useFinancials(ticker);

  if (isLoading) return <div className="p-4 text-sm text-gray-500">Loading financials…</div>;
  if (!data) return <div className="p-4 text-sm text-gray-400">No financial data available yet.</div>;

  const section = (data as Record<string, unknown>)[SECTION_MAP[tab]] as Record<string, MetricValue> | undefined;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 dark:text-white">Financial Results</h3>
        <span className="text-xs text-gray-400">{data.period} vs {data.comparison_period}</span>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              tab === t
                ? "bg-blue-600 text-white"
                : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <table className="w-full">
        <thead>
          <tr className="text-xs text-gray-400 border-b border-gray-200 dark:border-gray-700">
            <th className="pb-2 text-left font-medium">Metric</th>
            <th className="pb-2 text-right font-medium">{data.period}</th>
            <th className="pb-2 text-right font-medium">{data.comparison_period}</th>
            <th className="pb-2 text-right font-medium">YoY</th>
          </tr>
        </thead>
        <tbody>
          {section
            ? Object.entries(section).map(([key, metric]) => (
                <MetricRow key={key} label={LABEL_MAP[key] ?? key} metric={metric} />
              ))
            : null}
        </tbody>
      </table>

      {tab === "Income Statement" && data.returns?.annualised_roe?.current && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800 flex justify-between text-sm">
          <span className="text-gray-500">Annualised ROE</span>
          <span className="font-medium">
            {data.returns.annualised_roe.current}
            {data.returns.annualised_roe.direction && (
              <span className={`ml-2 text-xs ${data.returns.annualised_roe.direction === "increased" ? "text-green-500" : "text-red-500"}`}>
                {data.returns.annualised_roe.direction === "increased" ? "▲" : "▼"}
              </span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
