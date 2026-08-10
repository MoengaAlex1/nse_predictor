// Single source of truth for how prices, volumes, and deltas render across
// the investor shell. Every consumer should use these helpers so columns
// align (via tabular-nums), decimal counts match, and empty states share
// a consistent em-dash placeholder.

const emDash = "—";

const kesNf = new Intl.NumberFormat("en-KE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const compactNf = new Intl.NumberFormat("en-KE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

// KES 4,201.75 — comma-thousands + 2 decimals + prefix.
export function fmtKes(v: number | null | undefined, opts: { prefix?: boolean } = {}): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  const s = kesNf.format(v);
  return opts.prefix === false ? s : `KES ${s}`;
}

// 4.74 — 2 decimals, no prefix, no thousands separator (chart axes).
export function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  return compactNf.format(v);
}

// +3.04% / −1.21% — always signed, always 2 decimals.
export function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  const sign = v >= 0 ? "+" : "−"; // proper minus, not hyphen
  return `${sign}${Math.abs(v).toFixed(2)}%`;
}

// 23.44M / 5.13B / 998 — volume + shares outstanding + market cap.
export function fmtCompact(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  if (Math.abs(v) >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toLocaleString("en-KE");
}

// KES 79.2B — compact currency with KES prefix (market cap card).
export function fmtCompactKes(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  return `KES ${fmtCompact(v)}`;
}

// Absolute price change with proper minus glyph and 2 decimals; unsigned.
// Direction is conveyed by an adjacent arrow/color in the layout, not here.
export function fmtChangeAbs(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  return kesNf.format(Math.abs(v));
}

// Signed price change (e.g. "+0.14" / "−0.32") used inline with the pct.
export function fmtChangeSigned(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${kesNf.format(Math.abs(v))}`;
}

export const arrow = (up: boolean): string => (up ? "▲" : "▼"); // ▲ / ▼
export const trendClass = (v: number | null | undefined, mutedWhenNull = "text-hint"): string => {
  if (v == null) return mutedWhenNull;
  return v >= 0 ? "text-emerald-500" : "text-red-500";
};

export const EM_DASH = emDash;
