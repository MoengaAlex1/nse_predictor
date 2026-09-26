import { useState } from "react";
import type { FC } from "react";
import type { FinancialsDoc, NewsItem } from "../../types";
import { NewsPanel } from "./NewsPanel";
import { FilingsPanel } from "./FilingsPanel";

// One card, two tabs — user asked to combine "Filings & Corporate Filings
// Library" and "Latest News & Press Releases" into a single component.
// Neither underlying panel is deleted; both stay independently usable so
// nothing that already imports NewsPanel or FilingsPanel breaks.
type Tab = "news" | "filings";

interface Props {
  financials: FinancialsDoc | null | undefined;
  newsItems: NewsItem[];
  /** Which tab is visible on first render. Default is "news" because
   *  press releases are more time-sensitive than the filings library. */
  initial?: Tab;
}

const TABS: { key: Tab; label: string }[] = [
  { key: "news",    label: "News & Press Releases" },
  { key: "filings", label: "Filings & Corporate Actions" },
];

export const NewsAndFilingsPanel: FC<Props> = ({ financials, newsItems, initial = "news" }) => {
  const [tab, setTab] = useState<Tab>(initial);

  // Skip rendering entirely when neither tab would have anything to show —
  // matches the null-return contract each child already had, so the parent
  // page doesn't get a bare header with no data underneath.
  const newsCount = newsItems?.length ?? 0;
  const filingsCount =
    (financials?.announcements?.length ?? 0) +
    (financials?.corporate_actions?.length ?? 0) +
    (financials?.dividends?.length ?? 0);
  if (newsCount === 0 && filingsCount === 0) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-5 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          News &amp; Filings
        </p>
        <div className="flex gap-1">
          {TABS.map(({ key, label }) => {
            const isActive = key === tab;
            const count = key === "news" ? newsCount : filingsCount;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  isActive
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-rim bg-raised/50 text-sub hover:border-sub hover:text-ink"
                }`}
              >
                {label}
                <span
                  className={`rounded-full px-1.5 text-[10px] tabular-nums leading-none ${
                    isActive ? "bg-accent/20 text-accent" : "bg-surface text-hint"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Both child panels render self-contained (they have their own
          inner headers and filters). The tab we're on decides which one
          gets mounted, so the inner filters aren't shared — matches the
          user's mental model of "flip to filings, see filings filters". */}
      <div className="p-0">
        {tab === "news"    && <NewsPanel financials={financials} newsItems={newsItems} />}
        {tab === "filings" && financials && <FilingsPanel financials={financials} />}
      </div>
    </div>
  );
};
