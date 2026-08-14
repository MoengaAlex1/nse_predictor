import { useMemo, useState } from "react";
import type { FC } from "react";
import type { FinancialsDoc } from "../../types";

// External link + download icons
const ExtIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);
const SearchIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);
const ChevronIcon: FC<{ dir: "asc" | "desc" | null }> = ({ dir }) => (
  <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    className={`inline-block transition-transform ${dir === "asc" ? "rotate-180" : ""} ${dir == null ? "opacity-30" : "opacity-100"}`}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

type Tab = "all" | "results" | "actions" | "dividends";

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

type FilingRow = {
  date: string;
  title: string;
  url: string;
  category: "results" | "actions" | "dividends";
  type: string;
  source: string;      // "NSE" or "bulletin"
  amountKes?: number | null;
};

type SortKey = "date" | "title" | "type";
type SortDir = "asc" | "desc";

type Props = {
  financials: FinancialsDoc | null | undefined;
};

export const FilingsPanel: FC<Props> = ({ financials }) => {
  const [tab, setTab] = useState<Tab>("all");
  const [query, setQuery] = useState("");
  const [year, setYear] = useState<string>("all");
  const [source, setSource] = useState<"all" | "NSE" | "bulletin">("all");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // ── Normalise all three arrays into one uniform FilingRow[] ────────────
  const allRows = useMemo<FilingRow[]>(() => {
    const rows: FilingRow[] = [];

    for (const a of financials?.announcements ?? []) {
      if (!a.url || !a.title) continue;
      // Map announcement.type to our three UI buckets
      const cat: FilingRow["category"] =
        a.type === "dividend" ? "dividends" :
        a.type === "corporate_action" || a.type === "agm" ? "actions" :
        "results";
      rows.push({
        date: a.date,
        title: decode(a.title),
        url: a.url,
        category: cat,
        type: a.type,
        source: "NSE",
      });
    }
    for (const a of financials?.corporate_actions ?? []) {
      const t = (a as { title?: string; details?: string }).title
              ?? (a as { title?: string; details?: string }).details
              ?? "";
      const url = (a as { url?: string }).url;
      if (!t || !url) continue;
      rows.push({
        date: (a as { date?: string }).date ?? "",
        title: decode(t),
        url,
        category: "actions",
        type: a.type ?? "corporate_action",
        source: "NSE",
      });
    }
    for (const d of financials?.dividends ?? []) {
      const url = (d as { url?: string }).url;
      if (!url) continue;
      const titleFromRec = (d as { title?: string }).title;
      const title = titleFromRec
        ? decode(titleFromRec)
        : d.amount_kes != null
          ? `${d.type ?? "Dividend"} — KES ${d.amount_kes.toFixed(2)}/share`
          : `${d.type ?? "Dividend"} notice`;
      rows.push({
        date: d.announcement_date,
        title,
        url,
        category: "dividends",
        type: d.type ?? "dividend",
        source: (d as { source?: string }).source === "nse-daily-bulletin" ? "bulletin" : "NSE",
        amountKes: d.amount_kes,
      });
    }
    return rows;
  }, [financials]);

  const years = useMemo(() => {
    const s = new Set<string>();
    for (const r of allRows) {
      if (r.date && r.date.length >= 4) s.add(r.date.slice(0, 4));
    }
    return Array.from(s).sort().reverse();
  }, [allRows]);

  // ── Apply filters ──────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rs = allRows;
    if (tab !== "all") rs = rs.filter((r) => r.category === tab);
    if (year !== "all") rs = rs.filter((r) => r.date.startsWith(year));
    if (source !== "all") rs = rs.filter((r) => r.source === source);
    if (q) rs = rs.filter((r) =>
      r.title.toLowerCase().includes(q) || r.type.toLowerCase().includes(q)
    );
    const dir = sortDir === "asc" ? 1 : -1;
    rs = [...rs].sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      return String(av).localeCompare(String(bv)) * dir;
    });
    return rs;
  }, [allRows, tab, year, source, query, sortKey, sortDir]);

  const counts = useMemo(() => ({
    all:       allRows.length,
    results:   allRows.filter((r) => r.category === "results").length,
    actions:   allRows.filter((r) => r.category === "actions").length,
    dividends: allRows.filter((r) => r.category === "dividends").length,
  }), [allRows]);

  if (allRows.length === 0) return null;

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  };

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Filings & Corporate Filings Library
        </p>
        <div className="flex flex-wrap gap-1">
          <TabBtn label="All" count={counts.all} active={tab === "all"} onClick={() => setTab("all")} />
          <TabBtn label="Financial Results" count={counts.results} active={tab === "results"} onClick={() => setTab("results")} />
          <TabBtn label="Corporate Actions" count={counts.actions} active={tab === "actions"} onClick={() => setTab("actions")} />
          <TabBtn label="Dividends" count={counts.dividends} active={tab === "dividends"} onClick={() => setTab("dividends")} />
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2 border-b border-seam px-4 py-2.5">
        <div className="flex flex-1 items-center gap-2 rounded-md border border-seam bg-canvas px-2 py-1.5">
          <span className="text-hint"><SearchIcon /></span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search title or type..."
            className="flex-1 bg-transparent text-xs text-ink outline-none placeholder:text-hint"
            style={{ minWidth: 120 }}
          />
        </div>
        <select
          value={year}
          onChange={(e) => setYear(e.target.value)}
          className="rounded-md border border-seam bg-canvas px-2 py-1.5 text-xs text-ink outline-none"
        >
          <option value="all">All years</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as "all" | "NSE" | "bulletin")}
          className="rounded-md border border-seam bg-canvas px-2 py-1.5 text-xs text-ink outline-none"
        >
          <option value="all">All sources</option>
          <option value="NSE">NSE announcement</option>
          <option value="bulletin">Daily bulletin</option>
        </select>
        <span className="ml-auto text-[10px] text-hint">
          {filtered.length.toLocaleString()} / {allRows.length.toLocaleString()}
        </span>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-[92px_1fr_112px_78px_28px] items-center gap-2 border-b border-seam px-4 py-2 text-[10px] uppercase tracking-wider text-hint">
        <button type="button" onClick={() => toggleSort("date")} className="flex items-center gap-1 text-left font-semibold hover:text-ink">
          Date <ChevronIcon dir={sortKey === "date" ? sortDir : null} />
        </button>
        <button type="button" onClick={() => toggleSort("title")} className="flex items-center gap-1 text-left font-semibold hover:text-ink">
          Title <ChevronIcon dir={sortKey === "title" ? sortDir : null} />
        </button>
        <button type="button" onClick={() => toggleSort("type")} className="flex items-center gap-1 text-left font-semibold hover:text-ink">
          Type <ChevronIcon dir={sortKey === "type" ? sortDir : null} />
        </button>
        <span className="font-semibold">Source</span>
        <span />
      </div>

      <div className="max-h-[520px] overflow-y-auto py-1">
        {filtered.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-hint">
            No filings match these filters.
          </p>
        ) : (
          <div>
            {filtered.map((row, i) => <RowLine key={`${row.url}-${i}`} row={row} />)}
          </div>
        )}
      </div>
    </div>
  );
};

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
    <span className={`rounded-full px-1.5 text-[10px] tabular-nums leading-none ${
      active ? "bg-accent/20 text-accent" : "bg-surface text-hint"
    }`}>
      {count}
    </span>
  </button>
);

function typeBadgeStyle(category: FilingRow["category"], type: string): { label: string; cls: string } {
  const t = type.toLowerCase();
  if (category === "results") {
    if (t.includes("audited") || t.includes("annual")) {
      return { label: "AUDITED",   cls: "border-emerald-600/50 bg-emerald-500/10 text-emerald-500" };
    }
    return { label: "RESULT", cls: "border-sky-600/50 bg-sky-500/10 text-sky-500" };
  }
  if (category === "actions") {
    return { label: t.slice(0, 12).toUpperCase() || "ACTION", cls: "border-violet-600/50 bg-violet-500/10 text-violet-500" };
  }
  return { label: t.toUpperCase() || "DIV", cls: "border-amber-600/50 bg-amber-500/10 text-amber-500" };
}

const RowLine: FC<{ row: FilingRow }> = ({ row }) => {
  const badge = typeBadgeStyle(row.category, row.type);
  return (
    <a
      href={row.url}
      target="_blank"
      rel="noopener noreferrer"
      // Mobile: two-line card (title on top, meta row underneath) so the
      // date + badge + source don't force horizontal scroll on 375 px.
      // sm+: the original 5-col grid keeps the desktop density.
      className="group flex flex-col gap-1 px-4 py-2.5 text-xs transition-colors hover:bg-raised/60 sm:grid sm:grid-cols-[92px_1fr_112px_78px_28px] sm:items-center sm:gap-2 sm:py-2"
    >
      <span className="min-w-0 truncate text-sub group-hover:text-ink sm:order-2" title={row.title}>
        {row.title}
      </span>
      <div className="flex flex-wrap items-center gap-2 sm:contents">
        <span className="font-mono text-[10px] tabular-nums text-hint sm:order-1">
          {row.date || "—"}
        </span>
        <span className="sm:order-3">
          <span className={`inline-block max-w-[104px] truncate rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${badge.cls}`}>
            {badge.label}
          </span>
        </span>
        <span className="text-[10px] uppercase tracking-wider text-hint sm:order-4">
          {row.source === "bulletin" ? "BULLETIN" : "NSE"}
        </span>
        <span className="ml-auto text-hint group-hover:text-accent sm:order-5 sm:justify-self-end sm:ml-0" title="Open PDF">
          <ExtIcon />
        </span>
      </div>
    </a>
  );
};
