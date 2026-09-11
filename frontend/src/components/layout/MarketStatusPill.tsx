import type { FC } from "react";
import { useEffect, useState } from "react";
import { marketStatus } from "../../services/marketStatus";

/** OPEN/CLOSED pill with the next open in EAT. Ticks once a minute. */
export const MarketStatusPill: FC = () => {
  const [status, setStatus] = useState(() => marketStatus());

  useEffect(() => {
    const id = setInterval(() => setStatus(marketStatus()), 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="flex items-center gap-1.5 rounded-md border border-seam bg-raised/50 px-2 py-1"
      title={
        status.isOpen
          ? `NSE scheduled open · ${status.nowEat} EAT`
          : `NSE closed · opens ${status.nextOpen} EAT`
      }
    >
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          status.isOpen ? "bg-emerald-500" : "bg-hint"
        }`}
        aria-hidden="true"
      />
      <span className="text-[10px] font-semibold uppercase tracking-wider text-sub">
        {status.isOpen ? "Open" : "Closed"}
      </span>
      <span className="font-mono text-[10px] tabular-nums text-hint">
        {status.isOpen ? `${status.nowEat} EAT` : status.nextOpen}
      </span>
    </div>
  );
};
