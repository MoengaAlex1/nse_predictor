import type { FC } from "react";

const signalColors: Record<string, string> = {
  BUY: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  HOLD: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  SELL: "bg-red-500/20 text-red-400 border-red-500/30",
};

interface Props {
  signal: "BUY" | "HOLD" | "SELL";
  size?: "sm" | "lg";
}

export const SignalBadge: FC<Props> = ({ signal, size = "sm" }) => {
  const px =
    size === "lg"
      ? "px-4 py-2 text-sm font-bold"
      : "px-2 py-0.5 text-xs font-semibold";
  return (
    <span
      className={`inline-flex items-center rounded-full border ${px} ${signalColors[signal] ?? ""}`}
    >
      {signal}
    </span>
  );
};
