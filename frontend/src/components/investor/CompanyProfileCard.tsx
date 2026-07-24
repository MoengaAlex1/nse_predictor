import { useState } from "react";
import { getCompanyProfile } from "../../data/companyProfiles";
import type { CompanyDoc } from "../../types";

const TRUNCATE_LEN = 220;

interface Props {
  company: CompanyDoc;
}

function ProfileRow({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted uppercase tracking-wide">{label}</span>
      <span className="text-sm font-medium text-primary">{value ?? "—"}</span>
    </div>
  );
}

export function CompanyProfileCard({ company }: Props) {
  const [expanded, setExpanded] = useState(false);
  const profile = getCompanyProfile(company.ticker);
  const desc = company.description ?? "";
  const isLong = desc.length > TRUNCATE_LEN;
  const displayDesc = isLong && !expanded ? desc.slice(0, TRUNCATE_LEN) + "…" : desc;

  return (
    <section className="rounded-xl bg-surface border border-rim p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-primary">{company.name}</h2>
          <span className="text-xs text-muted mt-0.5 block">{company.sector}</span>
        </div>
        {profile.website && (
          <a
            href={`https://${profile.website}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-accent hover:underline shrink-0"
          >
            {profile.website}
          </a>
        )}
      </div>

      {desc && (
        <div className="text-sm text-secondary leading-relaxed">
          <span>{displayDesc}</span>
          {isLong && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="ml-1 text-accent text-xs hover:underline focus:outline-none"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t border-rim">
        <ProfileRow label="CEO" value={profile.ceo} />
        <ProfileRow label="Headquarters" value={profile.headquarters} />
        <ProfileRow label="Founded" value={profile.founded_year} />
        <ProfileRow label="Listed" value={profile.listing_year} />
        <ProfileRow
          label="Employees"
          value={profile.employees != null ? profile.employees.toLocaleString() : null}
        />
        <ProfileRow
          label="Shares (mn)"
          value={profile.shares_outstanding_mn != null ? profile.shares_outstanding_mn.toLocaleString() : null}
        />
      </div>
    </section>
  );
}
