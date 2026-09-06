import type { FC } from "react";
import { NavLink } from "react-router-dom";
import { CompanyLogo } from "../ui/CompanyLogo";
import { fmtPrice, fmtPct, arrow, trendClass, EM_DASH } from "../../lib/format";
import type { Quote } from "../../services/quotes";
import type { CompanyDoc } from "../../types";

/**
 * The security identity block, shared by /chart/:ticker and /company/:ticker
 * (phase 1 task 6). One header means switching view never changes the chrome —
 * the segmented control swaps the panel while keeping the ticker.
 */

type Props = {
  company: CompanyDoc | null | undefined;
  quote: Quote | null | undefined;
  /** Canonical doc id, used for both route targets. */
  id: string;
};

const segCls = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1 text-xs font-medium transition-colors ${
    isActive ? "bg-raised text-ink" : "text-sub hover:text-ink"
  }`;

export const SecurityHeader: FC<Props> = ({ company, quote, id }) => {
  const pct = quote?.changePct ?? null;
  const up = pct != null && pct >= 0;

  return (
    <header className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-seam pb-3">
      <CompanyLogo
        id={id}
        short={company?.short ?? id}
        color={company?.color ?? "#64748b"}
        icon={company?.icon ?? "🏢"}
      />

      <div className="min-w-0">
        <h1 className="truncate text-base font-bold text-ink">{company?.name ?? id}</h1>
        <p className="truncate font-mono text-[11px] text-hint">
          NSE:{company?.ticker ?? id}
          {company?.sector ? ` · ${company.sector}` : ""}
        </p>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="font-mono text-xl font-bold tabular-nums text-ink">
          {quote?.close != null ? `KES ${fmtPrice(quote.close)}` : EM_DASH}
        </span>
        <span className={`font-mono text-xs font-semibold tabular-nums ${trendClass(pct)}`}>
          {pct != null ? `${arrow(up)} ${fmtPct(pct)}` : EM_DASH}
        </span>
      </div>

      {/* Freshness is stated, never implied. */}
      {quote && (
        <p className="text-[10px] text-hint">
          {quote.isStale
            ? `Stale — last traded ${quote.date} (${quote.staleDays} trading days ago)`
            : `Last update ${quote.date}`}
          {quote.source !== "trade" && ` · ${quote.source.replace("-", " ")}`}
        </p>
      )}

      <div className="ml-auto flex overflow-hidden rounded-md border border-seam">
        <NavLink to={`/chart/${id}`} className={segCls}>Chart</NavLink>
        <NavLink to={`/company/${id}`} className={segCls}>Research</NavLink>
      </div>
    </header>
  );
};
