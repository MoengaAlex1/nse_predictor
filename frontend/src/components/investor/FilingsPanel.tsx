import { useState, useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc } from "../../types";

// External link icon
const ExtIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);

type Tab = "results" | "actions" | "dividends";

// Decode HTML entities that NSE's WordPress feed embeds in titles
// (e.g. "&#8211;" → "–"). Kept minimal — full DOMParser would be overkill.
function decode(s: string): string {
  return s
    .replace(/&#8211;/g, "–")
    .replace(/&#8212;/g, "—")
    .replace(/&amp;/g, "&")
    .replace(/&#8217;/g, "'")
    .replace(/&#8220;/g, "“")
    .replace(/&#8221;/g, "”")
    .replace(/&quot;/g, "\"");
}

const TabBtn: FC<{ label: string; count: number; active: boolean; onClick: () => void }> = ({
  label, count, active, onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
      active
        ? "border-accent bg-accent/10 text-accent"
        : "border-rim bg-raised/50 text-sub hover:border-sub hover:text-ink"
    }`}
  >
    {label}
    <span
      className={`rounded-full px-1.5 text-[10px] tabular-nums leading-none ${
        active ? "bg-accent/20 text-accent" : "bg-surface text-hint"
      }`}
    >
      {count}
    </span>
  </button>
);

type FilingRow = { date: string; title: string; url: string; type?: string };

const Row: FC<{ row: FilingRow; badge?: string; badgeColor?: string }> = ({ row, badge, badgeColor }) => (
  <a
    href={row.url}
    target="_blank"
    rel="noopener noreferrer"
    className="group flex items-start gap-3 rounded-md px-3 py-2 transition-colors hover:bg-raised/60"
  >
    <span className="w-20 shrink-0 pt-0.5 font-mono text-[10px] tabular-nums text-hint">
      {row.date || "—"}
    </span>
    {badge && (
      <span
        className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${badgeColor ?? "border-seam bg-raised text-hint"}`}
      >
        {badge}
      </span>
    )}
    <span className="flex-1 text-xs leading-snug text-sub group-hover:text-ink">
      {decode(row.title)}
    </span>
    <span className="shrink-0 pt-0.5 text-[10px] text-hint group-hover:text-accent">
      <ExtIcon />
    </span>
  </a>
);

type FilingsPanelProps = {
  financials: FinancialsDoc | null | undefined;
};

export const FilingsPanel: FC<FilingsPanelProps> = ({ financials }) => {
  const [tab, setTab] = useState<Tab>("results");

  const announcements = useMemo<FilingRow[]>(() => {
    return (financials?.announcements ?? [])
      .map((a) => ({ date: a.date, title: a.title, url: a.url, type: a.type }))
      .filter((a) => a.url)
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [financials?.announcements]);

  const actions = useMemo<FilingRow[]>(() => {
    return (financials?.corporate_actions ?? [])
      .map((a) => ({
        date: (a as { date?: string }).date ?? "",
        title: (a as { title?: string }).title ?? "",
        url: (a as { url?: string }).url ?? "",
        type: (a as { type?: string }).type,
      }))
      .filter((a) => a.url && a.title)
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [financials?.corporate_actions]);

  const dividends = useMemo<FilingRow[]>(() => {
    return (financials?.dividends ?? [])
      .map((d) => {
        const url = (d as { url?: string }).url ?? "";
        const title = (d as { title?: string }).title ?? "";
        const type = d.type;
        const amount = d.amount_kes;
        const derivedTitle =
          title ||
          (amount != null
            ? `${type ?? "Dividend"} — KES ${amount.toFixed(2)}/share`
            : `${type ?? "Dividend"} notice`);
        return { date: d.announcement_date, title: derivedTitle, url, type: type ?? undefined };
      })
      .filter((d) => d.url)
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [financials?.dividends]);

  const totalCount = announcements.length + actions.length + dividends.length;
  if (totalCount === 0) {
    return null;
  }

  const active =
    tab === "results" ? announcements : tab === "actions" ? actions : dividends;

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Filings & Reports
        </p>
        <div className="flex flex-wrap gap-1">
          <TabBtn
            label="Financial Results"
            count={announcements.length}
            active={tab === "results"}
            onClick={() => setTab("results")}
          />
          <TabBtn
            label="Corporate Actions"
            count={actions.length}
            active={tab === "actions"}
            onClick={() => setTab("actions")}
          />
          <TabBtn
            label="Dividends"
            count={dividends.length}
            active={tab === "dividends"}
            onClick={() => setTab("dividends")}
          />
        </div>
      </div>
      <div className="max-h-[420px] overflow-y-auto py-2">
        {active.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-hint">
            No records in this category.
          </p>
        ) : (
          <div className="space-y-0.5">
            {active.map((row, i) => {
              // Badge coloring per type
              let badge: string | undefined;
              let badgeColor: string | undefined;
              const t = (row.type ?? "").toLowerCase();
              if (tab === "results") {
                if (t.includes("audited") || t.includes("annual")) {
                  badge = "AUDITED";
                  badgeColor = "border-emerald-600/50 bg-emerald-500/10 text-emerald-500";
                } else if (t.includes("financial")) {
                  badge = "RESULT";
                  badgeColor = "border-sky-600/50 bg-sky-500/10 text-sky-500";
                }
              } else if (tab === "actions") {
                badge = "ACTION";
                badgeColor = "border-violet-600/50 bg-violet-500/10 text-violet-500";
              } else {
                badge = (row.type ?? "DIV").toUpperCase();
                badgeColor = "border-amber-600/50 bg-amber-500/10 text-amber-500";
              }
              return <Row key={i} row={row} badge={badge} badgeColor={badgeColor} />;
            })}
          </div>
        )}
      </div>
    </div>
  );
};
