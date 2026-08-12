import { useMemo } from "react";
import type { FC } from "react";
import type { FundamentalsDoc } from "../../types";
import { EM_DASH } from "../../lib/format";

type Props = {
  fundamentals: FundamentalsDoc | null | undefined;
};

const ROLE_ORDER = [
  "Chairperson", "Chair", "Chairman",
  "CEO", "Chief Executive", "Chief Executive Officer", "Group CEO", "Managing Director",
  "CFO", "Chief Finance", "Chief Financial Officer",
  "COO", "Chief Operating",
  "Executive Director",
  "Non-Executive", "Independent Director", "Director",
];

function roleRank(role: string): number {
  const r = role.toLowerCase();
  for (let i = 0; i < ROLE_ORDER.length; i += 1) {
    if (r.includes(ROLE_ORDER[i].toLowerCase())) return i;
  }
  return ROLE_ORDER.length;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 3);
}

export const LeadershipCard: FC<Props> = ({ fundamentals }) => {
  const board = useMemo(() => {
    const rows = fundamentals?.board_of_directors ?? [];
    return [...rows].sort((a, b) => roleRank(a.role) - roleRank(b.role));
  }, [fundamentals?.board_of_directors]);

  const summaryStats = useMemo(() => {
    const total = board.length;
    let executives = 0;
    let independents = 0;
    for (const d of board) {
      const r = d.role.toLowerCase();
      if (r.includes("independent")) independents += 1;
      else if (r.includes("ceo") || r.includes("cfo") || r.includes("coo") || r.includes("executive")) executives += 1;
    }
    return { total, executives, independents };
  }, [board]);

  if (board.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Leadership & Board
        </p>
        <p className="mt-3 text-xs text-hint">
          Board composition not yet extracted from the IR page.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Leadership & Board
        </p>
        <span className="font-mono text-[10px] text-hint">
          {summaryStats.total} directors · {summaryStats.independents} independent
        </span>
      </div>

      <ul className="max-h-[340px] overflow-y-auto">
        {board.map((d, i) => {
          const r = d.role.toLowerCase();
          const isChair = r.includes("chair");
          const isCEO = r.includes("ceo") || r.includes("chief executive") || r.includes("managing director");
          const isIndep = r.includes("independent");
          return (
            <li key={i} className="flex items-center gap-3 border-b border-seam/50 px-4 py-2.5 last:border-0">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold ${
                  isChair
                    ? "bg-amber-500/15 text-amber-500 ring-1 ring-amber-500/40"
                    : isCEO
                    ? "bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500/40"
                    : isIndep
                    ? "bg-sky-500/10 text-sky-400"
                    : "bg-slate-500/10 text-slate-400"
                }`}
              >
                {initials(d.name) || "—"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-ink">{d.name}</p>
                <p className="mt-0.5 truncate text-[10px] uppercase tracking-wider text-hint">
                  {d.role}
                  {d.appointment_date && <> · since {d.appointment_date.slice(0, 4)}</>}
                </p>
              </div>
              {(isChair || isCEO) && (
                <span
                  className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                    isChair
                      ? "border-amber-600/40 bg-amber-500/10 text-amber-500"
                      : "border-emerald-600/40 bg-emerald-500/10 text-emerald-500"
                  }`}
                >
                  {isChair ? "Chair" : "CEO"}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {(fundamentals?.credit_rating || summaryStats.total > 0) && (
        <div className="border-t border-seam px-4 py-2 text-[10px] text-hint">
          {fundamentals?.credit_rating ? (
            <span>
              Credit rating: <span className="font-mono text-ink">
                {fundamentals.credit_rating.agency} {fundamentals.credit_rating.rating}
              </span>
              {fundamentals.credit_rating.outlook && (
                <> · outlook {fundamentals.credit_rating.outlook}</>
              )}
              {fundamentals.credit_rating.as_of && (
                <> · {fundamentals.credit_rating.as_of}</>
              )}
            </span>
          ) : (
            <span>
              Governance: {summaryStats.executives} executive · {summaryStats.independents} independent · {summaryStats.total - summaryStats.executives - summaryStats.independents} other
            </span>
          )}
        </div>
      )}
      {summaryStats.total === 0 && <span className="text-hint">{EM_DASH}</span>}
    </div>
  );
};
