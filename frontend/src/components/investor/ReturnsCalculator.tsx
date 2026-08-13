import { useMemo, useState } from "react";
import type { FC } from "react";
import type { PricePoint, DividendEvent, FinancialsDoc } from "../../types";
import { fmtKes, fmtPct, EM_DASH } from "../../lib/format";

type Props = {
  ticker: string;
  history: PricePoint[];              // full price history (RTDB-loaded)
  financials?: FinancialsDoc | null;  // for dividends[]
  currentPrice: number | null;
};

const SAVINGS_ANNUAL_PCT = 10;        // rough Kenya money-market-fund rate
const NF_KES = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });

// Nearest-on-or-after price row for a target date. Returns null if history
// is empty or the whole history is before the target.
function priceOnOrAfter(history: PricePoint[], dateIso: string): PricePoint | null {
  for (const p of history) {
    if (p.date >= dateIso) return p;
  }
  return null;
}

// Sum of cash dividends per share collected between start and end.
// Reinvest mode: for each dividend, buy more shares at that day's price
// and roll forward. Returns { extraShares, cashCollected }.
function accumulateDividends(
  dividends: DividendEvent[],
  history: PricePoint[],
  startIso: string,
  endIso: string,
  initialShares: number,
  reinvest: boolean,
): { extraShares: number; cashCollected: number } {
  let extraShares = 0;
  let cashCollected = 0;
  let sharesRunning = initialShares;

  // Sort dividends chronologically by the best-available date.
  const dated: { date: string; amount: number }[] = [];
  for (const d of dividends ?? []) {
    if (d.amount_kes == null || d.amount_kes <= 0) continue;
    if (d.type === "scrip" || d.type === "bonus" || d.type === "none") continue;
    const date = d.ex_date || d.payment_date || d.announcement_date;
    if (!date) continue;
    if (date < startIso || date > endIso) continue;
    dated.push({ date, amount: d.amount_kes });
  }
  dated.sort((a, b) => a.date.localeCompare(b.date));

  for (const d of dated) {
    const dividendCash = sharesRunning * d.amount;
    if (reinvest) {
      const p = priceOnOrAfter(history, d.date);
      if (p && p.price > 0) {
        const boughtShares = dividendCash / p.price;
        extraShares += boughtShares;
        sharesRunning += boughtShares;
      } else {
        // No matching price row — bank the cash instead.
        cashCollected += dividendCash;
      }
    } else {
      cashCollected += dividendCash;
    }
  }
  return { extraShares, cashCollected };
}

type Preset = { label: string; yearsAgo: number | "ipo" };
const PRESETS: Preset[] = [
  { label: "1Y",  yearsAgo: 1 },
  { label: "3Y",  yearsAgo: 3 },
  { label: "5Y",  yearsAgo: 5 },
  { label: "10Y", yearsAgo: 10 },
  { label: "Max", yearsAgo: "ipo" },
];

const AMOUNT_PRESETS = [10_000, 50_000, 100_000, 500_000, 1_000_000];

function isoNYearsAgo(n: number): string {
  const t = new Date();
  t.setFullYear(t.getFullYear() - n);
  return t.toISOString().slice(0, 10);
}

export const ReturnsCalculator: FC<Props> = ({ ticker, history, financials, currentPrice }) => {
  const historyEarliestIso = history[0]?.date ?? "";
  const historyLatestIso = history[history.length - 1]?.date ?? "";
  const defaultStart = useMemo(() => {
    const wanted = isoNYearsAgo(3);
    return historyEarliestIso && wanted < historyEarliestIso ? historyEarliestIso : wanted;
  }, [historyEarliestIso]);

  const [amount, setAmount] = useState<number>(100_000);
  const [startDate, setStartDate] = useState<string>(defaultStart);
  const [reinvest, setReinvest] = useState<boolean>(true);

  const computed = useMemo(() => {
    if (!currentPrice || currentPrice <= 0 || !history.length || !amount || amount <= 0) {
      return null;
    }
    const startRow = priceOnOrAfter(history, startDate);
    if (!startRow || startRow.price <= 0) return null;

    const initialShares = amount / startRow.price;
    const { extraShares, cashCollected } = accumulateDividends(
      financials?.dividends ?? [],
      history,
      startRow.date,
      historyLatestIso,
      initialShares,
      reinvest,
    );

    const totalShares = initialShares + extraShares;
    const finalValue = totalShares * currentPrice + cashCollected;

    const gain = finalValue - amount;
    const totalReturnPct = (gain / amount) * 100;

    // CAGR (excludes cash yield curve — treats final as one bullet)
    const startT = new Date(startRow.date).getTime();
    const endT = new Date(historyLatestIso).getTime();
    const years = Math.max(0.001, (endT - startT) / (365.25 * 24 * 3600 * 1000));
    const cagr = years > 0.05 ? (Math.pow(finalValue / amount, 1 / years) - 1) * 100 : null;

    // Simple 10%/yr savings benchmark for the same period
    const savingsFinal = amount * Math.pow(1 + SAVINGS_ANNUAL_PCT / 100, years);
    const savingsBeat = finalValue - savingsFinal;

    return {
      startRow,
      startPrice: startRow.price,
      initialShares,
      extraShares,
      totalShares,
      cashCollected,
      finalValue,
      gain,
      totalReturnPct,
      cagr,
      years,
      savingsFinal,
      savingsBeat,
    };
  }, [amount, startDate, reinvest, history, historyLatestIso, financials?.dividends, currentPrice]);

  const applyPreset = (p: Preset) => {
    if (p.yearsAgo === "ipo") {
      if (historyEarliestIso) setStartDate(historyEarliestIso);
    } else {
      const target = isoNYearsAgo(p.yearsAgo);
      setStartDate(historyEarliestIso && target < historyEarliestIso ? historyEarliestIso : target);
    }
  };

  const hasData = history.length > 0 && currentPrice != null && currentPrice > 0;

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">
            Returns Calculator
          </p>
          <p className="mt-0.5 text-[11px] text-hint">
            What if you invested in {ticker} on a specific date?
          </p>
        </div>
        {historyEarliestIso && (
          <span className="font-mono text-[10px] text-hint">
            data since {historyEarliestIso}
          </span>
        )}
      </div>

      {/* Inputs */}
      <div className="grid gap-3 border-b border-seam p-4 md:grid-cols-[1fr_1fr_auto]">
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
            Amount (KES)
          </label>
          <input
            type="number"
            value={amount}
            min={1}
            step={1000}
            onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 0))}
            className="w-full rounded-md border border-seam bg-canvas px-2 py-1.5 font-mono text-sm tabular-nums text-ink outline-none focus:border-accent"
          />
          <div className="mt-1.5 flex flex-wrap gap-1">
            {AMOUNT_PRESETS.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setAmount(v)}
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold transition-colors ${
                  amount === v
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-seam bg-raised/40 text-hint hover:text-ink"
                }`}
              >
                {v >= 1_000_000 ? `${v / 1_000_000}M` : `${v / 1_000}K`}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
            Start date
          </label>
          <input
            type="date"
            value={startDate}
            min={historyEarliestIso || undefined}
            max={historyLatestIso || undefined}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-md border border-seam bg-canvas px-2 py-1.5 font-mono text-sm text-ink outline-none focus:border-accent"
          />
          <div className="mt-1.5 flex flex-wrap gap-1">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p)}
                className="rounded border border-seam bg-raised/40 px-1.5 py-0.5 text-[10px] font-semibold text-hint hover:text-ink"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col items-start justify-end">
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
            Dividends
          </label>
          <button
            type="button"
            onClick={() => setReinvest((v) => !v)}
            className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
              reinvest
                ? "border-emerald-600/40 bg-emerald-500/10 text-emerald-500"
                : "border-seam bg-raised/40 text-hint"
            }`}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${reinvest ? "bg-emerald-500" : "bg-slate-500"}`} />
            {reinvest ? "Reinvested" : "Cash only"}
          </button>
          <p className="mt-1 max-w-[140px] text-[9px] leading-tight text-hint">
            Reinvest each dividend into more shares at that day's price.
          </p>
        </div>
      </div>

      {/* Results */}
      {!hasData ? (
        <div className="p-4">
          <p className="text-xs text-hint">
            Waiting on price history and current price to run the calculation.
          </p>
        </div>
      ) : !computed ? (
        <div className="p-4">
          <p className="text-xs text-hint">
            No trading data on or after {startDate}. Try a later start date.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 border-b border-seam p-4 md:grid-cols-4">
            <Stat
              label="Final value"
              value={fmtKes(computed.finalValue)}
              accent={computed.gain >= 0 ? "up" : "down"}
              sub={`${computed.totalShares.toFixed(2)} shares`}
            />
            <Stat
              label="Total return"
              value={fmtPct(computed.totalReturnPct)}
              accent={computed.totalReturnPct >= 0 ? "up" : "down"}
              sub={(computed.gain >= 0 ? "+" : "−") + fmtKes(Math.abs(computed.gain))}
            />
            <Stat
              label="CAGR"
              value={computed.cagr != null ? fmtPct(computed.cagr) : EM_DASH}
              accent={computed.cagr != null && computed.cagr >= 0 ? "up" : "down"}
              sub={`over ${computed.years.toFixed(1)} years`}
            />
            <Stat
              label={reinvest ? "Extra shares from divs" : "Dividends received"}
              value={
                reinvest
                  ? computed.extraShares > 0
                    ? `+${computed.extraShares.toFixed(2)}`
                    : "0.00"
                  : fmtKes(computed.cashCollected)
              }
              accent="neutral"
              sub={
                reinvest
                  ? `${computed.initialShares.toFixed(2)} → ${computed.totalShares.toFixed(2)}`
                  : "Cash pile"
              }
            />
          </div>

          {/* Narrative + savings benchmark */}
          <div className="space-y-2 px-4 py-3 text-xs text-sub">
            <p>
              <span className="text-hint">You bought</span>{" "}
              <span className="font-mono font-semibold text-ink">
                {computed.initialShares.toFixed(2)}
              </span>{" "}
              <span className="text-hint">shares of</span>{" "}
              <span className="font-semibold text-ink">{ticker}</span>{" "}
              <span className="text-hint">at</span>{" "}
              <span className="font-mono text-ink">
                {fmtKes(computed.startPrice, { prefix: true })}
              </span>{" "}
              <span className="text-hint">
                on {computed.startRow.date}
                {computed.startRow.date !== startDate && (
                  <> (nearest trading day)</>
                )}
              </span>
              .
            </p>
            <p>
              <span className="text-hint">If instead you'd earned a flat</span>{" "}
              <span className="font-mono text-ink">{SAVINGS_ANNUAL_PCT}%/yr</span>{" "}
              <span className="text-hint">from a money-market fund, the same</span>{" "}
              <span className="font-mono text-ink">KES {NF_KES.format(amount)}</span>{" "}
              <span className="text-hint">would now be</span>{" "}
              <span className="font-mono font-semibold text-ink">
                {fmtKes(computed.savingsFinal)}
              </span>
              <span className="text-hint">. {ticker} beat that benchmark by</span>{" "}
              <span
                className={`font-mono font-semibold ${
                  computed.savingsBeat >= 0 ? "text-emerald-500" : "text-red-500"
                }`}
              >
                {computed.savingsBeat >= 0 ? "+" : "−"}
                {fmtKes(Math.abs(computed.savingsBeat), { prefix: true })}
              </span>
              .
            </p>
          </div>
        </>
      )}
    </div>
  );
};

const Stat: FC<{
  label: string;
  value: string;
  sub?: string;
  accent: "up" | "down" | "neutral";
}> = ({ label, value, sub, accent }) => {
  const color =
    accent === "up"
      ? "text-emerald-500"
      : accent === "down"
      ? "text-red-500"
      : "text-ink";
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">
        {label}
      </p>
      <p className={`mt-0.5 font-mono text-lg font-bold tabular-nums ${color}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 font-mono text-[10px] text-hint">{sub}</p>}
    </div>
  );
};
