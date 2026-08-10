import type { FC } from "react";
import { PeerChip } from "../ui/PeerChip";
import { usePeers } from "../../hooks/usePeers";

type QuickCompareRowProps = {
  ticker: string;
  sector: string | null | undefined;
};

export const QuickCompareRow: FC<QuickCompareRowProps> = ({ ticker, sector }) => {
  const peers = usePeers(ticker, sector);

  if (peers.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">
          Quick Compare
        </p>
        <p className="text-xs text-hint">
          {sector ? "No sector peers with recent price data." : "Sector unknown — cannot list peers yet."}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Quick Compare</p>
        <p className="text-[10px] text-hint">{sector}</p>
      </div>
      <div className="flex gap-2 overflow-x-auto scrollbar-none">
        {peers.map((p) => (
          <PeerChip key={p.ticker} peer={p} />
        ))}
      </div>
    </div>
  );
};
