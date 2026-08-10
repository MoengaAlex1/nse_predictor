import type { FC } from "react";
import { Link } from "react-router-dom";
import { CompanyLogo } from "./CompanyLogo";
import type { CompanyDoc } from "../../types";

type PeerChipProps = {
  peer: CompanyDoc;
};

export const PeerChip: FC<PeerChipProps> = ({ peer }) => {
  const pct = peer.change_pct_today;
  const up = pct != null && pct >= 0;

  return (
    <Link
      to={`/chart/${peer.ticker}`}
      className="flex min-w-[152px] items-center gap-2 rounded-lg border border-seam bg-raised/50 px-2.5 py-1.5 transition-colors hover:border-rim hover:bg-raised"
    >
      <CompanyLogo id={peer.id} short={peer.short} color={peer.color} icon={peer.icon} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-ink">{peer.short}</p>
        <p className="truncate font-mono text-[10px] text-hint">{peer.ticker}</p>
      </div>
      <div className="text-right">
        {peer.current_price != null && (
          <p className="font-mono text-xs font-semibold text-ink">{peer.current_price.toFixed(2)}</p>
        )}
        {pct != null && (
          <p className={`font-mono text-[10px] ${up ? "text-emerald-500" : "text-red-500"}`}>
            {up ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
          </p>
        )}
      </div>
    </Link>
  );
};
