import { useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc } from "../../types";
import { fmtKes } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
};

type Marker = {
  date: string;
  monthKey: string;    // YYYY-MM
  dayFrac: number;     // 0..1 position within the month strip
  type: "final" | "interim" | "special" | "other";
  amountKes: number | null;
  label: string;
};

const TYPE_STYLE: Record<Marker["type"], string> = {
  final:   "bg-emerald-500",
  interim: "bg-sky-500",
  special: "bg-amber-500",
  other:   "bg-slate-400",
};

function classify(type: string | null | undefined): Marker["type"] {
  const t = (type ?? "").toLowerCase();
  if (t.includes("final"))   return "final";
  if (t.includes("interim")) return "interim";
  if (t.includes("special")) return "special";
  return "other";
}

function monthsWindow(): { key: string; label: string; short: string }[] {
  // 6 months back to 6 months forward, anchored on this month
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth() - 6, 1);
  const out: { key: string; label: string; short: string }[] = [];
  for (let i = 0; i < 13; i += 1) {
    const d = new Date(start.getFullYear(), start.getMonth() + i, 1);
    const y = d.getFullYear();
    const m = d.getMonth() + 1;
    const key = `${y}-${String(m).padStart(2, "0")}`;
    const short = d.toLocaleString("en-KE", { month: "short" });
    out.push({ key, label: `${short} ${y}`, short });
  }
  return out;
}

export const ExDateCalendarStrip: FC<Props> = ({ financials }) => {
  const months = useMemo(() => monthsWindow(), []);
  const monthKeys = useMemo(() => new Set(months.map((m) => m.key)), [months]);

  const markers = useMemo<Marker[]>(() => {
    const out: Marker[] = [];
    for (const d of financials?.dividends ?? []) {
      const dateStr = d.ex_date || d.payment_date;
      if (!dateStr) continue;
      const key = dateStr.slice(0, 7);
      if (!monthKeys.has(key)) continue;

      const daysInMonth = new Date(
        parseInt(dateStr.slice(0, 4), 10),
        parseInt(dateStr.slice(5, 7), 10),
        0,
      ).getDate();
      const day = parseInt(dateStr.slice(8, 10), 10);
      out.push({
        date: dateStr,
        monthKey: key,
        dayFrac: (day - 1) / Math.max(1, daysInMonth - 1),
        type: classify(d.type),
        amountKes: d.amount_kes,
        label: [
          d.ex_date === dateStr ? "Ex-date" : "Payment",
          d.type ? d.type.replace(/^./, (c) => c.toUpperCase()) : "Dividend",
          d.amount_kes != null ? fmtKes(d.amount_kes) : null,
        ].filter(Boolean).join(" · "),
      });
    }
    return out;
  }, [financials, monthKeys]);

  const markersByMonth = useMemo(() => {
    const m = new Map<string, Marker[]>();
    for (const mk of markers) {
      const arr = m.get(mk.monthKey) ?? [];
      arr.push(mk);
      m.set(mk.monthKey, arr);
    }
    return m;
  }, [markers]);

  if (markers.length === 0) return null;

  const todayKey = new Date().toISOString().slice(0, 7);

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Ex-Date Calendar
        </p>
        <div className="flex flex-wrap gap-2 text-[10px] text-hint">
          <Legend color="bg-emerald-500" label="Final" />
          <Legend color="bg-sky-500" label="Interim" />
          <Legend color="bg-amber-500" label="Special" />
        </div>
      </div>

      <div
        className="mt-3 grid gap-0.5"
        style={{ gridTemplateColumns: "repeat(13, minmax(0, 1fr))" }}
      >
        {months.map((mo) => {
          const isCurrent = mo.key === todayKey;
          const marks = markersByMonth.get(mo.key) ?? [];
          return (
            <div
              key={mo.key}
              className={`relative flex h-16 flex-col rounded border ${
                isCurrent
                  ? "border-accent/50 bg-accent/5"
                  : "border-seam bg-canvas/60"
              }`}
              title={`${mo.label}${marks.length ? ` · ${marks.length} event${marks.length === 1 ? "" : "s"}` : ""}`}
            >
              <span className={`mb-auto px-1 pt-0.5 text-[8px] font-mono uppercase tracking-wider ${
                isCurrent ? "text-accent" : "text-hint"
              }`}>
                {mo.short}
              </span>
              <div className="relative h-4">
                {marks.map((mk, i) => (
                  <span
                    key={i}
                    title={`${mk.date} · ${mk.label}`}
                    className={`absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-canvas ${TYPE_STYLE[mk.type]}`}
                    style={{ left: `${mk.dayFrac * 100}%` }}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-2 text-[10px] text-hint">
        Last 6 + next 6 months · hover a dot for detail · current month outlined
      </p>
    </div>
  );
};

const Legend: FC<{ color: string; label: string }> = ({ color, label }) => (
  <span className="inline-flex items-center gap-1">
    <span className={`inline-block h-1.5 w-1.5 rounded-full ${color}`} />
    {label}
  </span>
);
