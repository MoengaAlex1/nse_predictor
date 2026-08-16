import type { FC } from "react";
import { CompanyLogo } from "../ui/CompanyLogo";
import { useWatchlist } from "../../hooks/useWatchlist";
import { fmtKes, fmtChangeSigned, fmtPct, arrow, trendClass, EM_DASH } from "../../lib/format";
import type { CompanyDoc } from "../../types";

const StarIcon: FC<{ filled?: boolean }> = ({ filled }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

const ShareIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
  </svg>
);

const CompareIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 6h13l-3-3" />
    <path d="M20 18H7l3 3" />
  </svg>
);

type HeaderButtonProps = {
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
  title?: string;
  onClick?: () => void;
  active?: boolean;
};

const HeaderButton: FC<HeaderButtonProps> = ({
  label,
  icon,
  disabled,
  title,
  onClick,
  active,
}) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onClick}
    title={title ?? (disabled ? "Coming soon" : undefined)}
    className={`flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition-colors ${
      active
        ? "border-accent bg-accent/10 text-accent"
        : disabled
        ? "cursor-not-allowed border-seam bg-raised/50 text-hint"
        : "border-rim bg-raised text-ink hover:bg-raised/70"
    }`}
  >
    {icon}
    <span>{label}</span>
  </button>
);

type PriceHeaderProps = {
  company: CompanyDoc | null | undefined;
  ticker: string;
  currentPrice: number | null;
  changeAbs: number | null;
  changePct: number | null;
  priceAsOf?: string | null;
};

export const PriceHeader: FC<PriceHeaderProps> = ({
  company,
  ticker,
  currentPrice,
  changeAbs,
  changePct,
  priceAsOf,
}) => {
  const up = changePct != null && changePct >= 0;
  const trendColor = trendClass(changePct);

  const { isAuthenticated, has, add, remove, isPending } = useWatchlist();
  const isWatched = has(ticker);
  const watchlistLabel = !isAuthenticated
    ? "Watchlist"
    : isWatched
    ? "Watching"
    : "Watchlist";
  const watchlistTitle = !isAuthenticated
    ? "Sign in to add to watchlist"
    : isWatched
    ? `Remove ${ticker} from watchlist`
    : `Add ${ticker} to watchlist`;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {company && (
            // id must be the Firestore short-form (SGL, SCOM) rather than
            // the URL ticker (SGL.NR) so /logos/${id}.png resolves.
            <CompanyLogo
              id={company.id}
              short={company.short}
              color={company.color}
              icon={company.icon}
              size="lg"
            />
          )}
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <h1 className="truncate text-lg font-bold text-ink">
                {company?.name ?? ticker}
              </h1>
              <span className="shrink-0 font-mono text-xs font-semibold text-muted">{ticker}</span>
            </div>
            <p className="mt-0.5 truncate text-[11px] uppercase tracking-wider text-hint">
              Nairobi Securities Exchange
              {company?.sector && <> · {company.sector}</>}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <HeaderButton
            label={watchlistLabel}
            icon={<StarIcon filled={isWatched} />}
            title={watchlistTitle}
            disabled={!isAuthenticated || isPending}
            active={isAuthenticated && isWatched}
            onClick={() => (isWatched ? remove(ticker) : add(ticker))}
          />
          <HeaderButton label="Share" icon={<ShareIcon />} disabled title="Share — coming soon" />
          <HeaderButton label="Compare" icon={<CompareIcon />} disabled title="Compare — coming soon" />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {currentPrice != null ? (
          <span className="font-mono text-4xl font-black leading-none text-ink tabular-nums">
            {fmtKes(currentPrice)}
          </span>
        ) : (
          <span className="text-2xl text-hint">{EM_DASH}</span>
        )}
        <FreshnessChip
          isLive={company?.price_is_live ?? null}
          updatedAt={company?.price_updated_at ?? null}
        />
        {changeAbs != null && changePct != null && (
          <span className={`font-mono text-sm font-semibold tabular-nums ${trendColor}`}>
            {arrow(up)} {fmtChangeSigned(changeAbs)} ({fmtPct(changePct)})
          </span>
        )}
      </div>
      <FreshnessLine
        isLive={company?.price_is_live ?? null}
        updatedAt={company?.price_updated_at ?? null}
        priceAsOf={priceAsOf ?? null}
      />
    </div>
  );
};

// ── Freshness helpers ────────────────────────────────────────────────────────

const EAT_TZ = "Africa/Nairobi";

function formatEatTime(iso: string): string | null {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  return t.toLocaleTimeString("en-KE", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: EAT_TZ,
  });
}

function formatEatDate(iso: string): string | null {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  return t.toLocaleDateString("en-KE", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: EAT_TZ,
  });
}

// Small pill sitting inline with the price. Shows LIVE (green) when the
// current push came from an intraday tier, or "At close" (muted) otherwise.
const FreshnessChip: FC<{ isLive: boolean | null; updatedAt: string | null }> = ({
  isLive,
  updatedAt,
}) => {
  if (isLive === true) {
    const timeStr = updatedAt ? formatEatTime(updatedAt) : null;
    return (
      <span
        title="Live intraday price from NSE — ~15 minute delay"
        className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400"
      >
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
        </span>
        Live{timeStr ? ` · ${timeStr} EAT` : ""}
      </span>
    );
  }
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
      At close
    </span>
  );
};

// Second line under the price with the source and delay disclaimer.
// Live → "Updated HH:MM EAT · ~15 min delayed"
// EOD  → "Closing price · YYYY-MM-DD"
const FreshnessLine: FC<{
  isLive: boolean | null;
  updatedAt: string | null;
  priceAsOf: string | null;
}> = ({ isLive, updatedAt, priceAsOf }) => {
  if (isLive === true) {
    const timeStr = updatedAt ? formatEatTime(updatedAt) : null;
    const dateStr = updatedAt ? formatEatDate(updatedAt) : null;
    return (
      <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-hint">
        <span>
          {dateStr && `${dateStr} · `}Updated{timeStr ? ` ${timeStr} EAT` : ""} · ~15 min delayed
        </span>
        <span className="rounded border border-emerald-500/30 bg-emerald-500/5 px-1.5 py-0.5 font-mono uppercase tracking-wider text-emerald-400">
          Intraday
        </span>
      </p>
    );
  }
  if (priceAsOf) {
    return (
      <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-hint">
        <span>Closing price · {priceAsOf}</span>
        <span className="rounded border border-seam bg-raised px-1.5 py-0.5 font-mono uppercase tracking-wider">
          EOD only
        </span>
      </p>
    );
  }
  return null;
};
