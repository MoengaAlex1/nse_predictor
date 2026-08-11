import { useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc } from "../../types";
import { fmtKes, EM_DASH } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
};

type Event = {
  date: string;
  label: string;
  amountKes?: number | null;
  daysAway: number;
  kind: "ex-date" | "payment" | "agm" | "results-expected";
};

const KIND_COLOR: Record<Event["kind"], string> = {
  "ex-date":          "border-amber-600/40 bg-amber-500/10 text-amber-500",
  "payment":          "border-emerald-600/40 bg-emerald-500/10 text-emerald-500",
  "agm":              "border-sky-600/40 bg-sky-500/10 text-sky-500",
  "results-expected": "border-violet-600/40 bg-violet-500/10 text-violet-500",
};

function daysBetween(a: string, b: string): number {
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  return Math.round((da - db) / (1000 * 60 * 60 * 24));
}

export const UpcomingEventsCard: FC<Props> = ({ financials }) => {
  const events = useMemo<Event[]>(() => {
    const today = new Date().toISOString().slice(0, 10);
    const out: Event[] = [];

    for (const d of financials?.dividends ?? []) {
      if (d.ex_date && d.ex_date > today) {
        out.push({
          date: d.ex_date,
          label: `Ex-date · ${(d.type ?? "dividend").replace(/^./, (c) => c.toUpperCase())}`,
          amountKes: d.amount_kes,
          daysAway: daysBetween(d.ex_date, today),
          kind: "ex-date",
        });
      }
      if (d.payment_date && d.payment_date > today) {
        out.push({
          date: d.payment_date,
          label: `Payment · ${(d.type ?? "dividend").replace(/^./, (c) => c.toUpperCase())}`,
          amountKes: d.amount_kes,
          daysAway: daysBetween(d.payment_date, today),
          kind: "payment",
        });
      }
    }

    // Sort chronological, next 3
    out.sort((a, b) => a.date.localeCompare(b.date));
    return out.slice(0, 4);
  }, [financials]);

  if (events.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Upcoming Events
        </p>
        <p className="mt-2 text-[11px] text-hint">
          No scheduled ex-dates or payments on record.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        Upcoming Events
      </p>
      <ul className="mt-3 space-y-2">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-2">
            <span
              className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${KIND_COLOR[e.kind]}`}
            >
              {e.kind}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[11px] text-ink">{e.label}</p>
              <p className="mt-0.5 flex items-baseline gap-2 font-mono text-[10px] tabular-nums text-hint">
                <span>{e.date}</span>
                <span className="rounded bg-raised px-1 text-[9px]">
                  in {e.daysAway}d
                </span>
                {e.amountKes != null && (
                  <span className="ml-auto text-amber-500">{fmtKes(e.amountKes)}</span>
                )}
                {e.amountKes == null && (
                  <span className="ml-auto text-hint">{EM_DASH}</span>
                )}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};
