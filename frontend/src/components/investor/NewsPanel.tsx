import { useState, useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc, NewsItem } from "../../types";

type Category = "all" | "earnings" | "dividend" | "regulatory" | "agm" | "corporate_action";

const CATEGORY_COLORS: Record<string, string> = {
  earnings:         "bg-emerald-900/40 text-emerald-400 border-emerald-800",
  dividend:         "bg-sky-900/40 text-sky-400 border-sky-800",
  regulatory:       "bg-amber-900/40 text-amber-400 border-amber-800",
  agm:              "bg-violet-900/40 text-violet-400 border-violet-800",
  corporate_action: "bg-orange-900/40 text-orange-400 border-orange-800",
  general:          "bg-slate-800/60 text-slate-400 border-slate-700",
  financial_result: "bg-emerald-900/40 text-emerald-400 border-emerald-800",
};

const SOURCE_COLORS: Record<string, string> = {
  NSE:     "border-slate-600 text-slate-400",
  scraper: "border-indigo-700 text-indigo-400",
};

function nseTypeToCategory(type: string): NewsItem["category"] {
  if (type === "financial_result") return "earnings";
  if (type === "dividend") return "dividend";
  if (type === "agm") return "agm";
  if (type === "corporate_action") return "corporate_action";
  return "general";
}

function daysAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr + "T00:00:00").getTime()) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 30) return `${diff} days ago`;
  if (diff < 365) return `${Math.round(diff / 30)} months ago`;
  return `${Math.round(diff / 365)} years ago`;
}

function mergeAndDeduplicate(financials: FinancialsDoc | null | undefined, newsItems: NewsItem[]): NewsItem[] {
  const fromAnnouncements: NewsItem[] = (financials?.announcements ?? []).map((a) => ({
    id: `nse-${a.date}-${a.title.slice(0, 20)}`,
    date: a.date,
    title: a.title,
    category: nseTypeToCategory(a.type),
    body: null,
    url: a.url || null,
    source: "NSE" as const,
  }));

  const all = [...newsItems, ...fromAnnouncements].sort((a, b) => {
    const dateD = b.date.localeCompare(a.date);
    if (dateD !== 0) return dateD;
    return a.source === "scraper" ? -1 : 1;
  });

  const seen = new Set<string>();
  return all.filter((item) => {
    const key = `${item.date}-${item.title.slice(0, 24).trim().toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

interface Props {
  financials: FinancialsDoc | null | undefined;
  newsItems: NewsItem[];
}

const PAGE_SIZE = 5;

export const NewsPanel: FC<Props> = ({ financials, newsItems }) => {
  const [activeCategory, setActiveCategory] = useState<Category>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const merged = useMemo(() => mergeAndDeduplicate(financials, newsItems), [financials, newsItems]);

  const filtered =
    activeCategory === "all"
      ? merged
      : merged.filter((item) => item.category === activeCategory);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = filtered.length > visibleCount;

  const categories: { key: Category; label: string }[] = [
    { key: "all",              label: "All"               },
    { key: "earnings",         label: "Earnings"          },
    { key: "dividend",         label: "Dividends"         },
    { key: "regulatory",       label: "Regulatory"        },
    { key: "corporate_action", label: "Corporate Actions" },
  ];

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-5 py-3">
        <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
          Latest News &amp; Press Releases
        </p>
        <div className="flex flex-wrap gap-1.5">
          {categories.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => { setActiveCategory(key); setVisibleCount(PAGE_SIZE); }}
              className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                activeCategory === key
                  ? "bg-sky-600 text-white"
                  : "text-muted hover:bg-rim hover:text-sub"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {merged.length === 0 ? (
        <p className="px-5 py-6 text-sm text-muted">No announcements on record for this company.</p>
      ) : (
        <div className="divide-y divide-seam/40">
          {visible.map((item) => (
            <div key={item.id} className="px-5 py-4 hover:bg-raised/20 transition-colors">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-semibold text-hint">{daysAgo(item.date)}</span>
                <span className="text-[10px] text-hint">· {item.date}</span>
                <span className={`ml-auto rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${SOURCE_COLORS[item.source] ?? SOURCE_COLORS.NSE}`}>
                  {item.source}
                </span>
                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${CATEGORY_COLORS[item.category] ?? CATEGORY_COLORS.general}`}>
                  {item.category.replace("_", " ")}
                </span>
              </div>

              <p className="text-sm font-medium text-ink">{item.title}</p>

              {openId === item.id && item.body && (
                <p className="mt-2 text-sm leading-relaxed text-sub">{item.body}</p>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-3">
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-semibold text-sky-400 hover:text-sky-300"
                  >
                    ↗ View NSE filing
                  </a>
                ) : item.body ? (
                  <button
                    type="button"
                    onClick={() => setOpenId(openId === item.id ? null : item.id)}
                    className="text-xs font-semibold text-sky-400 hover:text-sky-300"
                  >
                    {openId === item.id ? "Show less ▲" : "Read more ▼"}
                  </button>
                ) : null}
              </div>
            </div>
          ))}

          {hasMore && (
            <div className="px-5 py-3">
              <button
                type="button"
                onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                className="text-xs font-semibold text-sky-400 hover:text-sky-300"
              >
                Load more ↓ ({filtered.length - visibleCount} remaining)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
