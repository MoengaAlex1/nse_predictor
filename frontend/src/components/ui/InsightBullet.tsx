import type { FC } from "react";

export type InsightTone = "good" | "warn" | "neutral";

const TONE_STYLES: Record<InsightTone, { color: string; symbol: string }> = {
  good: { color: "text-emerald-500", symbol: "✓" },
  warn: { color: "text-red-500", symbol: "⚠" },
  neutral: { color: "text-hint", symbol: "○" },
};

type InsightBulletProps = {
  tone: InsightTone;
  children: React.ReactNode;
};

export const InsightBullet: FC<InsightBulletProps> = ({ tone, children }) => {
  const style = TONE_STYLES[tone];
  return (
    <li className="flex items-start gap-2 py-1.5">
      <span
        className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${style.color}`}
        aria-hidden="true"
      >
        {style.symbol}
      </span>
      <span className="text-xs leading-relaxed text-sub">{children}</span>
    </li>
  );
};
