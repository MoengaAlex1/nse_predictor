import type { FC } from "react";
import type { PriceStatus } from "../../types";

interface Props {
  status: PriceStatus | null;
  /** Trading day the status describes (EAT, YYYY-MM-DD). */
  statusDate: string | null;
  /** HH:MM EAT of the latest provisional snapshot. */
  asOf?: string;
  className?: string;
}

/**
 * Shows whether the displayed price is still moving or has settled.
 *
 * The NSE publishes its official daily report PDF only after the 15:00 EAT
 * close, so during the session the price on screen is the live last-traded
 * figure and can still change. This makes that distinction visible instead of
 * leaving every price looking equally authoritative.
 *
 * Renders nothing when the pipeline has not labelled the price — an unlabelled
 * price is better shown bare than mislabelled as settled.
 */
export const PriceStatusBadge: FC<Props> = ({ status, statusDate, asOf, className }) => {
  if (status === null) return null;

  const isFinal = status === "final";

  const tone = isFinal
    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
    : "border-amber-500/30 bg-amber-500/10 text-amber-400";

  const label = isFinal ? "Final" : "Provisional";

  const detail = isFinal
    ? `Settled close${statusDate ? ` for ${statusDate}` : ""}, from the official NSE daily report`
    : `Live last-traded price${asOf ? ` as of ${asOf} EAT` : ""} — not settled until the NSE daily report is published after the 15:00 EAT close`;

  return (
    <span
      data-testid="price-status-badge"
      data-status={status}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tone} ${className ?? ""}`}
      title={detail}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${isFinal ? "bg-emerald-400" : "bg-amber-400 animate-pulse"}`}
      />
      <span>{label}</span>
      {!isFinal && asOf ? (
        <span className="font-normal normal-case tracking-normal">{asOf}</span>
      ) : null}
      <span className="sr-only">. {detail}</span>
    </span>
  );
};
