import { useState, useRef, useEffect } from "react";
import type { FC } from "react";
import { useCompanies } from "../../hooks/useCompanies";
import { fmtPct, arrow, trendClass } from "../../lib/format";
import { shortFromDisplayTicker } from "../../lib/identity";
import type { CompanyDoc } from "../../types";

const XIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const PlusIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

type ChipMeta = { short: string; color: string; changePct: number | null };

const Chip: FC<{ label: string; color: string; changePct: number | null; removable: boolean; onRemove?: () => void }> = ({
  label,
  color,
  changePct,
  removable,
  onRemove,
}) => {
  const up = changePct != null && changePct >= 0;
  return (
    <span className="flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-seam bg-raised/50 pl-2 pr-1 text-[11px]">
      <span
        className="inline-block h-2 w-2 rounded-sm"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="font-semibold text-ink">{label}</span>
      {changePct != null && (
        <span className={`font-mono tabular-nums ${trendClass(changePct)}`}>
          {arrow(up)} {fmtPct(changePct)}
        </span>
      )}
      {removable ? (
        <button
          type="button"
          onClick={onRemove}
          className="flex h-4 w-4 items-center justify-center rounded-full text-hint transition-colors hover:bg-rim hover:text-ink"
          aria-label={`Remove ${label} from compare`}
        >
          <XIcon />
        </button>
      ) : (
        <span className="w-1" />
      )}
    </span>
  );
};

type CompareControlsProps = {
  primary: { ticker: string; short: string; color: string; changePct: number | null };
  compareTickers: string[];
  compareMeta: Map<string, ChipMeta>;
  onAdd: (ticker: string) => void;
  onRemove: (ticker: string) => void;
  suggested: CompanyDoc[];
  maxCompare?: number;
};

export const CompareControls: FC<CompareControlsProps> = ({
  primary,
  compareTickers,
  compareMeta,
  onAdd,
  onRemove,
  suggested,
  maxCompare = 4,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { data: companies = [] } = useCompanies();

  const atCap = compareTickers.length >= maxCompare;
  // Post primary-key refactor: exclude by short-form id ("SCOM"), not the
  // display ticker. Any of primary.ticker / compareTickers can arrive in
  // either form ("SCOM" or "SCOM.NR") — shortFromDisplayTicker normalises.
  const excluded = new Set([
    shortFromDisplayTicker(primary.ticker),
    ...compareTickers.map(shortFromDisplayTicker),
  ]);
  const eligible = companies.filter((c) => !excluded.has(c.id));

  const results = query.trim()
    ? eligible
        .filter((c) => {
          const q = query.toLowerCase();
          return (
            c.ticker.toLowerCase().includes(q) ||
            c.short.toLowerCase().includes(q) ||
            c.name.toLowerCase().includes(q)
          );
        })
        .slice(0, 6)
    : suggested.filter((c) => !excluded.has(c.id)).slice(0, 6);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
        setActiveIdx(-1);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const pick = (ticker: string) => {
    onAdd(ticker);
    setQuery("");
    setActiveIdx(-1);
    if (compareTickers.length + 1 >= maxCompare) setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    }
    if (e.key === "Enter" && activeIdx >= 0 && results[activeIdx]) {
      pick(results[activeIdx].ticker);
    }
  };

  return (
    // NOTE: this outer row deliberately has NO overflow rule. Setting
    // overflow-x-auto (or scrollbar-none via overflow-x) here would
    // implicitly clip Y — the "Add" dropdown pops down inside this row
    // and would be sliced off. Only the inner chip strip scrolls.
    <div className="flex items-center gap-2 border-b border-seam px-4 py-2">
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-hint">
        Compare to
      </span>

      <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto scrollbar-none">
        <Chip
          label={primary.short}
          color={primary.color}
          changePct={primary.changePct}
          removable={false}
        />

        {compareTickers.map((t) => {
          const meta = compareMeta.get(t) ?? { short: t, color: "#94a3b8", changePct: null };
          return (
            <Chip
              key={t}
              label={meta.short}
              color={meta.color}
              changePct={meta.changePct}
              removable
              onRemove={() => onRemove(t)}
            />
          );
        })}
      </div>

      <div ref={containerRef} className="relative shrink-0">
        <button
          type="button"
          onClick={() => !atCap && setOpen((o) => !o)}
          disabled={atCap}
          title={atCap ? `Max ${maxCompare} comparisons` : "Add a company to compare"}
          className={`flex h-7 items-center gap-1 rounded-full border px-2.5 text-[11px] font-semibold transition-colors ${
            atCap
              ? "cursor-not-allowed border-seam bg-raised/40 text-hint"
              : open
              ? "border-accent bg-accent/10 text-accent"
              : "border-dashed border-rim bg-raised/40 text-muted hover:border-accent hover:text-accent"
          }`}
        >
          <PlusIcon />
          <span>{atCap ? `Max ${maxCompare}` : "Add"}</span>
        </button>

        {open && (
          <div className="absolute right-0 top-full z-50 mt-1 w-72 overflow-hidden rounded-xl border border-rim bg-surface shadow-xl">
            <div className="border-b border-seam px-3 py-2">
              <input
                ref={inputRef}
                type="text"
                placeholder="Search company or ticker…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIdx(-1);
                }}
                onKeyDown={onKeyDown}
                className="w-full bg-transparent text-sm text-ink placeholder:text-hint outline-none"
              />
            </div>
            <div className="max-h-64 overflow-y-auto py-1">
              {results.length === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-hint">
                  {query ? `No matches for "${query}"` : "All sector peers already added."}
                </p>
              ) : (
                <>
                  {!query && (
                    <p className="px-3 pt-1 pb-0.5 text-[10px] font-semibold uppercase tracking-wider text-hint">
                      Sector peers
                    </p>
                  )}
                  {results.map((c, i) => (
                    <button
                      key={c.ticker}
                      type="button"
                      onClick={() => pick(c.ticker)}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left transition-colors ${
                        i === activeIdx ? "bg-raised" : "hover:bg-raised/60"
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-ink">{c.short}</p>
                        <p className="truncate text-[10px] text-hint">{c.name}</p>
                      </div>
                      <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted">
                        {c.ticker}
                      </span>
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
