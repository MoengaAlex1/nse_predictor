import { useMemo, useState } from "react";
import type { FC } from "react";
import { getCompanyProfile } from "../../data/companyProfiles";
import type { CompanyDoc, FundamentalsDoc } from "../../types";
import { fmtCompact, EM_DASH } from "../../lib/format";

const TRUNCATE_LEN = 320;

type Props = {
  company: CompanyDoc;
  fundamentals?: FundamentalsDoc | null;
};

function ProfileRow({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-hint">{label}</span>
      <span className="text-xs font-medium text-ink">{value ?? EM_DASH}</span>
    </div>
  );
}

// Prefer Firestore data (fresh from IR pipeline) → fundamentals → static fallback.
function pick<T>(...vals: (T | null | undefined)[]): T | null {
  for (const v of vals) if (v !== null && v !== undefined && v !== "") return v as T;
  return null;
}

export const CompanyProfileCard: FC<Props> = ({ company, fundamentals }) => {
  const [expanded, setExpanded] = useState(false);
  const staticFallback = getCompanyProfile(company.ticker);

  // Merge every source into one profile snapshot. Precedence: Firestore
  // company doc → Firestore fundamentals doc → static bundled fallback.
  const profile = useMemo(() => ({
    ceo:                  pick(company.ceo, fundamentals?.ceo, staticFallback.ceo),
    chairperson:          fundamentals?.chairperson ?? null,
    industry:             fundamentals?.industry ?? null,
    address:              fundamentals?.address ?? null,
    headquarters:         pick(fundamentals?.address, staticFallback.headquarters),
    isin:                 fundamentals?.isin ?? null,
    listing_date:         fundamentals?.listing_date ?? null,
    listing_year:         pick(
                            fundamentals?.listing_date ? parseInt(fundamentals.listing_date.slice(0,4), 10) : null,
                            staticFallback.listing_year,
                          ),
    founded_year:         pick(fundamentals?.founded_year, staticFallback.founded_year),
    employees:            pick(company.employees, fundamentals?.employees, staticFallback.employees),
    shares_outstanding_mn: pick(fundamentals?.shares_outstanding_mn, staticFallback.shares_outstanding_mn),
    website:              staticFallback.website,
    ir_enriched_at:       pick(company.ir_enriched_at, fundamentals?.ir_enriched_at),
  }), [company, fundamentals, staticFallback]);

  const desc = company.description ?? "";
  const isLong = desc.length > TRUNCATE_LEN;
  const displayDesc = isLong && !expanded ? desc.slice(0, TRUNCATE_LEN) + "…" : desc;

  const enrichedRelative = useMemo(() => {
    if (!profile.ir_enriched_at) return null;
    const t = new Date(profile.ir_enriched_at);
    if (Number.isNaN(t.getTime())) return null;
    const days = Math.round((Date.now() - t.getTime()) / (24 * 3600 * 1000));
    if (days === 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 30) return `${days}d ago`;
    return `${Math.round(days / 30)}mo ago`;
  }, [profile.ir_enriched_at]);

  return (
    <section className="rounded-xl border border-rim bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-seam pb-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-ink">{company.name}</h2>
          <p className="mt-0.5 text-[10px] uppercase tracking-wider text-hint">
            About {company.short}
            {profile.industry && <> · {profile.industry}</>}
            {!profile.industry && <> · {company.sector}</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          {profile.website && (
            <a
              href={profile.website.startsWith("http") ? profile.website : `https://${profile.website}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-accent/40 bg-accent/10 px-2 py-0.5 font-semibold text-accent hover:bg-accent/20"
            >
              IR page ↗
            </a>
          )}
          {enrichedRelative && (
            <span className="text-hint" title={profile.ir_enriched_at ?? ""}>
              enriched {enrichedRelative}
            </span>
          )}
        </div>
      </div>

      {desc ? (
        <p className="mt-3 text-xs leading-relaxed text-sub">
          {displayDesc}
          {isLong && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="ml-1 text-[11px] font-semibold text-accent hover:underline"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </p>
      ) : (
        <p className="mt-3 text-xs italic text-hint">
          No business description on file yet. Runs of the IR enrichment pipeline populate this.
        </p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-seam pt-3 sm:grid-cols-3 lg:grid-cols-4">
        <ProfileRow label="CEO" value={profile.ceo} />
        <ProfileRow label="Chairperson" value={profile.chairperson} />
        <ProfileRow label="Headquarters" value={profile.headquarters} />
        <ProfileRow
          label="Founded"
          value={profile.founded_year != null ? String(profile.founded_year) : null}
        />
        <ProfileRow
          label="Listed"
          value={profile.listing_year != null ? String(profile.listing_year) : null}
        />
        <ProfileRow label="ISIN" value={profile.isin} />
        <ProfileRow
          label="Employees"
          value={profile.employees != null ? profile.employees.toLocaleString() : null}
        />
        <ProfileRow
          label="Shares outstanding"
          value={profile.shares_outstanding_mn != null
            ? `${fmtCompact(profile.shares_outstanding_mn * 1_000_000)}`
            : null}
        />
      </div>
    </section>
  );
};
