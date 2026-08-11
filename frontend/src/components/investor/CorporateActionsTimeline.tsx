import { useMemo, useState } from "react";
import type { FC } from "react";
import type { FinancialsDoc } from "../../types";
import { EM_DASH } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
};

type Entry = {
  date: string;
  year: string;
  kind: "dividend" | "bonus" | "scrip" | "split" | "rights" | "agm" | "restructuring" | "regulatory" | "other";
  headline: string;
  detail: string;
  url?: string;
  amountKes?: number | null;
  exDate?: string | null;
  paymentDate?: string | null;
};

// Icon + colour per action type
const KIND_STYLE: Record<Entry["kind"], { icon: string; ring: string; text: string; label: string }> = {
  dividend:      { icon: "◆", ring: "bg-amber-500 ring-amber-500/40",   text: "text-amber-500",   label: "Dividend" },
  bonus:         { icon: "❖", ring: "bg-purple-500 ring-purple-500/40", text: "text-purple-500",  label: "Bonus" },
  scrip:         { icon: "❖", ring: "bg-purple-500 ring-purple-500/40", text: "text-purple-500",  label: "Scrip" },
  split:         { icon: "◫", ring: "bg-sky-500 ring-sky-500/40",       text: "text-sky-500",     label: "Split" },
  rights:        { icon: "▲", ring: "bg-blue-500 ring-blue-500/40",     text: "text-blue-500",    label: "Rights Issue" },
  agm:           { icon: "●", ring: "bg-emerald-500 ring-emerald-500/40", text: "text-emerald-500", label: "AGM" },
  restructuring: { icon: "▶", ring: "bg-red-500 ring-red-500/40",       text: "text-red-500",     label: "Restructuring" },
  regulatory:    { icon: "■", ring: "bg-orange-500 ring-orange-500/40", text: "text-orange-500",  label: "Regulatory" },
  other:         { icon: "○", ring: "bg-slate-500 ring-slate-500/40",   text: "text-slate-400",   label: "Notice" },
};

function classifyType(rawType: string, title: string): Entry["kind"] {
  const t = (rawType + " " + title).toLowerCase();
  if (t.includes("bonus"))     return "bonus";
  if (t.includes("scrip"))     return "scrip";
  if (t.includes("split"))     return "split";
  if (t.includes("rights"))    return "rights";
  if (t.includes("agm") || t.includes("annual general")) return "agm";
  if (t.includes("restructur") || t.includes("merger") || t.includes("delisting")) return "restructuring";
  if (t.includes("regulator") || t.includes("suspension")) return "regulatory";
  if (t.includes("dividend") || t.includes("interim") || t.includes("final")) return "dividend";
  return "other";
}

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

export const CorporateActionsTimeline: FC<Props> = ({ financials }) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const entries = useMemo<Entry[]>(() => {
    const out: Entry[] = [];

    for (const d of financials?.dividends ?? []) {
      if (!d.announcement_date) continue;
      const kind = classifyType(d.type ?? "dividend", "");
      const headline =
        d.amount_kes != null
          ? `${(d.type ?? "Dividend").replace(/^./, (c) => c.toUpperCase())} — KES ${d.amount_kes.toFixed(2)}/share`
          : `${(d.type ?? "Dividend").replace(/^./, (c) => c.toUpperCase())} declared`;
      out.push({
        date: d.announcement_date,
        year: d.announcement_date.slice(0, 4),
        kind,
        headline,
        detail: [
          d.period ? `Period: ${d.period}` : null,
          d.ex_date ? `Ex-date: ${d.ex_date}` : null,
          d.payment_date ? `Payment: ${d.payment_date}` : null,
        ].filter(Boolean).join(" · "),
        url: (d as { url?: string }).url,
        amountKes: d.amount_kes,
        exDate: d.ex_date,
        paymentDate: d.payment_date,
      });
    }

    for (const a of financials?.corporate_actions ?? []) {
      const date = (a as { date?: string }).date ?? "";
      if (!date) continue;
      const title = decode((a as { title?: string; details?: string }).title
        ?? (a as { details?: string }).details
        ?? "");
      const kind = classifyType(a.type ?? "", title);
      out.push({
        date,
        year: date.slice(0, 4),
        kind,
        headline: title || `${KIND_STYLE[kind].label} notice`,
        detail: a.type ?? "",
        url: (a as { url?: string }).url,
      });
    }

    for (const a of financials?.announcements ?? []) {
      if (!a.date || !a.title) continue;
      // Skip financial-result announcements — they belong in the financials
      // table / filings panel, not the corporate-actions timeline.
      if (a.type === "financial_result") continue;
      const kind = classifyType(a.type ?? "", a.title);
      out.push({
        date: a.date,
        year: a.date.slice(0, 4),
        kind,
        headline: decode(a.title),
        detail: a.type ?? "",
        url: a.url,
      });
    }

    // Dedup by (date + first 40 chars of headline)
    const seen = new Set<string>();
    const deduped: Entry[] = [];
    for (const e of out.sort((a, b) => b.date.localeCompare(a.date))) {
      const key = `${e.date}::${e.headline.slice(0, 40).toLowerCase()}`;
      if (seen.has(key)) continue;
      seen.add(key);
      deduped.push(e);
    }
    return deduped;
  }, [financials]);

  // Group by year for section headers (must run every render — no early
  // return before hooks).
  const groups = useMemo(() => {
    const g = new Map<string, Entry[]>();
    for (const e of entries) {
      if (!g.has(e.year)) g.set(e.year, []);
      g.get(e.year)!.push(e);
    }
    return Array.from(g.entries()); // preserved insertion order = date desc
  }, [entries]);

  if (entries.length === 0) return null;

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Corporate Actions Timeline
        </p>
        <span className="font-mono text-[10px] text-hint">
          {entries.length} events · {groups.length} years
        </span>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 border-b border-seam px-4 py-2 text-[10px] text-hint">
        {(["dividend", "bonus", "split", "rights", "agm"] as const).map((k) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${KIND_STYLE[k].ring.split(" ")[0]}`} />
            {KIND_STYLE[k].label}
          </span>
        ))}
      </div>

      <div className="max-h-[600px] overflow-y-auto px-4 py-3">
        {groups.map(([year, items]) => (
          <div key={year} className="mb-4 last:mb-0">
            <h3 className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-hint">
              {year}
            </h3>
            <ul className="relative space-y-2 border-l border-seam pl-4">
              {items.map((e, i) => {
                const id = `${e.date}-${i}`;
                const isExpanded = expanded.has(id);
                const style = KIND_STYLE[e.kind];
                return (
                  <li key={id} className="relative">
                    <span
                      className={`absolute -left-[21px] top-1.5 inline-block h-2.5 w-2.5 rounded-full ring-2 ${style.ring}`}
                      aria-hidden
                    />
                    <button
                      type="button"
                      onClick={() => toggle(id)}
                      className="group w-full rounded-md px-2 py-1.5 text-left transition-colors hover:bg-raised/60"
                    >
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="font-mono text-[10px] tabular-nums text-hint">
                          {e.date}
                        </span>
                        <span className={`text-[10px] font-bold uppercase tracking-wider ${style.text}`}>
                          {style.icon} {style.label}
                        </span>
                        <span className="min-w-0 truncate text-xs text-ink group-hover:text-ink">
                          {e.headline}
                        </span>
                      </div>
                      {isExpanded && (
                        <div className="mt-1.5 border-t border-seam pt-1.5 text-[11px] text-sub">
                          {e.detail && <p>{e.detail}</p>}
                          <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-hint">
                            {e.amountKes != null && <span>Amount: KES {e.amountKes.toFixed(2)}</span>}
                            {e.exDate && <span>Ex-date: {e.exDate}</span>}
                            {e.paymentDate && <span>Payment: {e.paymentDate}</span>}
                            {!e.detail && !e.amountKes && !e.exDate && (
                              <span className="text-hint">{EM_DASH} no additional detail</span>
                            )}
                            {e.url && (
                              <a
                                href={e.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(ev) => ev.stopPropagation()}
                                className="ml-auto text-accent hover:underline"
                              >
                                Open PDF ↗
                              </a>
                            )}
                          </div>
                        </div>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
};
