import type { FC } from "react";
import { Link } from "react-router-dom";
import type { CompanyDoc, IndexReading, MarketOverviewDoc } from "../../types";

type Props = {
  market: MarketOverviewDoc;
  companies: CompanyDoc[];
};

type Bucket = "up-strong" | "up" | "flat" | "down" | "down-strong" | "no-data";

// Equity buckets: ±5% breakpoint. Indices use ±1% because index moves are
// order-of-magnitude smaller (NSE 20 moving 5% in a day is a black-swan
// event; 1% is already a heavy session).
function bucketFor(pct: number | null | undefined, strongAt: number): Bucket {
  if (pct == null) return "no-data";
  if (pct >= strongAt) return "up-strong";
  if (pct > 0) return "up";
  if (pct === 0) return "flat";
  if (pct > -strongAt) return "down";
  return "down-strong";
}

const TILE_BG: Record<Bucket, string> = {
  "up-strong":   "bg-emerald-600/90 border-emerald-500/50",
  "up":          "bg-emerald-800/70 border-emerald-700/40",
  "flat":        "bg-raised/60 border-seam",
  "down":        "bg-red-800/70 border-red-700/40",
  "down-strong": "bg-red-600/90 border-red-500/50",
  "no-data":     "bg-raised/40 border-seam/60",
};

const PCT_COLOR: Record<Bucket, string> = {
  "up-strong":   "text-emerald-50",
  "up":          "text-emerald-100",
  "flat":        "text-sub",
  "down":        "text-red-100",
  "down-strong": "text-red-50",
  "no-data":     "text-hint",
};

// Panel row order matches the NSE Daily Report layout so the heatmap looks
// like the official summary anyone at NSE / a broker desk will recognise.
const INDEX_ORDER: { key: string; label: string; unit?: string }[] = [
  { key: "NASI",   label: "NASI" },
  { key: "NSE20",  label: "NSE 20" },
  { key: "NSE10",  label: "NSE 10" },
  { key: "NSE25",  label: "NSE 25" },
  { key: "NSEBSI", label: "NSE BSI" },
  { key: "MCAP",   label: "M.CAP", unit: "KSh Bn" },
];

function formatPrice(p: number | null | undefined): string {
  if (p == null) return "—";
  if (p >= 1000) return p.toLocaleString("en-KE", { maximumFractionDigits: 2 });
  return p.toFixed(2);
}

function formatPct(p: number | null | undefined): string {
  if (p == null) return "N/A";
  if (Math.abs(p) < 0.005) return "Flat";
  return `${p >= 0 ? "▲" : "▼"} ${Math.abs(p).toFixed(2)}%`;
}

function formatIndex(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(v: number | null | undefined): string {
  if (v == null) return "";
  if (v === 0) return "0 shares";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(v >= 10_000_000 ? 0 : 1)}M`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}k`;
  return `${Math.round(v)}`;
}

// Days between an ISO date string and today. Returns Infinity when the input
// is malformed so callers can treat it as "very stale". Using UTC dates keeps
// the calculation stable across timezone boundaries — the +/-3h EAT offset
// never crosses a date line in practice for our use case.
function ageInDays(iso: string | null | undefined): number {
  if (!iso) return Infinity;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return Infinity;
  const days = (Date.now() - then) / 86_400_000;
  return Math.floor(days);
}

// Build the small caption that appears under each tile's price. This is
// the trust-signal — it distinguishes:
//   - "Flat · 4.9M" (real trading, price genuinely unchanged)
//   - "Flat · 0 shares" (no trades today, price is yesterday's close)
//   - "Stale · Jul 24" (data hasn't refreshed in a while)
// so a "Flat" tile can no longer read as "broken" when it's honest.
function tileCaption(c: {
  change_pct_today: number | null | undefined;
  volume_today?: number | null;
  price_date: string | null | undefined;
}): { text: string; tone: "muted" | "warn" | "stale" } {
  const age = ageInDays(c.price_date);
  if (age > 5) {
    // Data older than a trading week — surface the age instead of volume.
    const label = c.price_date ? new Date(c.price_date).toLocaleDateString("en-KE", {
      month: "short", day: "numeric",
    }) : "no date";
    return { text: `Stale · ${label}`, tone: "stale" };
  }
  const v = c.volume_today;
  const flat = c.change_pct_today != null && Math.abs(c.change_pct_today) < 0.005;
  if (v === 0) {
    return { text: flat ? "No trades today" : "0 shares", tone: "warn" };
  }
  if (v != null && v > 0) {
    return { text: formatVolume(v), tone: "muted" };
  }
  // Volume unknown (mirror doesn't have it yet) — leave blank rather than
  // making up a placeholder that reads as "0 trades".
  return { text: "", tone: "muted" };
}

export const MarketHeatmap: FC<Props> = ({ market, companies }) => {
  const sorted = [...companies].sort((a, b) => a.short.localeCompare(b.short));

  let gainers = 0, losers = 0, unchanged = 0, noData = 0;
  for (const c of companies) {
    const p = c.change_pct_today;
    if (p == null) noData++;
    else if (p > 0) gainers++;
    else if (p < 0) losers++;
    else unchanged++;
  }

  const indexMap: Record<string, IndexReading> = market.indices ?? {};
  const indices = INDEX_ORDER
    .map(spec => {
      const reading = indexMap[spec.key];
      return reading ? { ...spec, reading } : null;
    })
    .filter((x): x is { key: string; label: string; unit?: string; reading: IndexReading } => x != null);

  const asOfLabel = market.indices_updated_at
    ? new Date(market.indices_updated_at).toLocaleString("en-KE", {
        dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Nairobi",
      }) + " EAT"
    : market.date;

  return (
    <section className="overflow-hidden rounded-xl border border-rim bg-surface">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-seam/60 px-5 py-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-ink">NSE Market Heatmap</h2>
          <p className="text-[11px] text-muted">1D performance as at {asOfLabel}</p>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <div className="text-center">
            <p className="font-semibold uppercase tracking-wider text-muted">Gainers</p>
            <p className="mt-0.5 font-mono text-base font-bold text-emerald-500">{gainers}</p>
          </div>
          <div className="text-center">
            <p className="font-semibold uppercase tracking-wider text-muted">Losers</p>
            <p className="mt-0.5 font-mono text-base font-bold text-red-500">{losers}</p>
          </div>
          <div className="text-center">
            <p className="font-semibold uppercase tracking-wider text-muted">Unchanged</p>
            <p className="mt-0.5 font-mono text-base font-bold text-sub">{unchanged}</p>
          </div>
        </div>
      </header>

      {/* Legend */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam/40 px-5 py-2 text-[10px]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-semibold text-emerald-400">Gainers {gainers}</span>
          <span className="rounded-full bg-raised px-2 py-0.5 font-semibold text-sub">Unchanged {unchanged}</span>
          <span className="rounded-full bg-red-500/10 px-2 py-0.5 font-semibold text-red-400">Losers {losers}</span>
          {noData > 0 && (
            <span className="rounded-full bg-raised/50 px-2 py-0.5 font-semibold text-hint">No Data {noData}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <span className="text-muted">Equities (±5%)</span>
            <span className="h-3 w-4 rounded-sm bg-emerald-600/90" title="≥ +5%" />
            <span className="h-3 w-4 rounded-sm bg-emerald-800/70" title="0 – +5%" />
            <span className="h-3 w-4 rounded-sm bg-raised/60"      title="Flat" />
            <span className="h-3 w-4 rounded-sm bg-red-800/70"     title="0 – -5%" />
            <span className="h-3 w-4 rounded-sm bg-red-600/90"     title="≤ -5%" />
          </div>
        </div>
      </div>

      {/* Tile grid */}
      <div className="grid grid-cols-3 gap-1.5 p-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-9">
        {sorted.map(c => {
          const b = bucketFor(c.change_pct_today, 5);
          const caption = tileCaption(c);
          const captionClass =
            caption.tone === "stale" ? "text-amber-400"
            : caption.tone === "warn" ? "text-hint italic"
            : "text-sub";
          const tooltipParts = [
            `${c.short} · ${c.name}`,
            c.price_date ? `Price as of ${c.price_date}` : null,
            c.volume_today != null ? `Volume: ${c.volume_today.toLocaleString("en-KE")} shares` : null,
          ].filter(Boolean);
          return (
            <Link
              key={c.id || c.ticker}
              to={`/chart/${c.ticker}`}
              className={`group flex min-h-[76px] flex-col rounded-md border p-2 transition-transform hover:scale-[1.03] ${TILE_BG[b]}`}
              title={tooltipParts.join(" · ")}
            >
              <p className="text-[11px] font-bold leading-tight text-ink">{c.short}</p>
              <p className="truncate text-[9px] leading-tight text-sub">{c.name}</p>
              <p className={`mt-auto font-mono text-[11px] font-semibold leading-tight ${PCT_COLOR[b]}`}>
                {formatPct(c.change_pct_today)}
              </p>
              <p className="font-mono text-[9px] leading-tight text-sub">
                KSh {formatPrice(c.current_price)}
              </p>
              {caption.text && (
                <p className={`font-mono text-[9px] leading-tight ${captionClass}`}>
                  {caption.text}
                </p>
              )}
            </Link>
          );
        })}
      </div>

      {/* Indices row — real values from NSE Market Statistics feed */}
      {indices.length > 0 && (
        <div className="border-t border-seam/60 px-3 pb-3 pt-2">
          <div className="mb-1.5 flex items-baseline justify-between px-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">NSE Share Indices</p>
            <p className="text-[9px] text-hint">Source: nse.co.ke / market-statistics</p>
          </div>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-6">
            {indices.map(({ key, label, unit, reading }) => {
              const b = bucketFor(reading.change_pct, 1);
              return (
                <div
                  key={key}
                  className={`rounded-md border px-3 py-2 ${TILE_BG[b]}`}
                  title={`${label} · ${reading.value.toLocaleString("en-KE")} (${reading.change_points >= 0 ? "+" : ""}${reading.change_points.toFixed(2)} pts)`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-bold text-ink">{label}</p>
                    <p className={`font-mono text-[11px] font-semibold ${PCT_COLOR[b]}`}>
                      {formatPct(reading.change_pct)}
                    </p>
                  </div>
                  <div className="mt-0.5 flex items-baseline justify-between gap-2">
                    <p className="font-mono text-[13px] font-semibold text-ink">
                      {formatIndex(reading.value)}
                    </p>
                    {unit && <p className="text-[9px] text-hint">{unit}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-seam/60 px-5 py-2 text-[10px] text-hint">
        <span>Source: NSE market data</span>
        <span>
          {companies.length} equities · {indices.length} indices
        </span>
      </footer>
    </section>
  );
};
