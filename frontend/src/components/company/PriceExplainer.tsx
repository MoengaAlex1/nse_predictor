import type { FC } from "react";
import { useMemo, useState } from "react";
import type { CompanyDoc, TechnicalsDoc, PricePoint, CorporateEvent } from "../../types/index";

// ── Sector educational context ─────────────────────────────────────────────────
const SECTOR_NOTES: Record<string, string> = {
  "Banking":
    "Banks profit from the gap between lending rates and deposit rates (the \"net interest margin\"). When the Central Bank of Kenya raises its benchmark rate, bank margins often widen — which can lift share prices. Watch for quarterly earnings and NPL (non-performing loan) ratios as key signals.",
  "Telecommunication and Technology":
    "Telcos earn from voice, data, and mobile-money services. Subscriber growth and data revenue per user (ARPU) are the metrics that move these stocks. Government spectrum decisions and M-Pesa-style fintech expansion are sector-specific catalysts to watch.",
  "Energy and Petroleum":
    "Energy stocks track global oil prices and local fuel demand. When global crude prices rise, margins for downstream distributors can compress even as upstream producers benefit. Government pricing controls in Kenya add another layer of unpredictability.",
  "Manufacturing and Allied":
    "Manufacturing margins are squeezed by input costs (energy, raw materials, imported components) and can be hurt by a weak KES. When the shilling depreciates, import costs rise. Strong consumer spending and export contracts are positive signals.",
  "Insurance":
    "Insurers earn premium income and invest the float. Rising interest rates increase investment returns, often boosting profitability. Claims ratios and regulatory capital requirements are the key risk factors to monitor.",
  "Commercial and Services":
    "These companies are sensitive to consumer confidence and discretionary spending. Economic slowdowns tend to hurt them first; recoveries lift them early.",
  "Real Estate Investment Trust":
    "REITs distribute most of their income as dividends, so they are valued like bonds — they become more attractive when interest rates fall. Occupancy rates and rental yields are the core metrics.",
  "Agricultural":
    "Agricultural stocks are highly sensitive to rainfall, commodity prices, and seasonal cycles. A poor harvest or falling global commodity prices can quickly affect margins.",
  "Investment":
    "Investment holding companies are valued at a discount or premium to their Net Asset Value (NAV) — the sum of their portfolio. Track the underlying assets to understand price moves.",
};

// ── Analysis functions ─────────────────────────────────────────────────────────
interface Move {
  startDate: string;
  endDate: string;
  startPrice: number;
  endPrice: number;
  pct: number;
}

function findSignificantMoves(data: PricePoint[]): Move[] {
  if (data.length < 10) return [];

  // Divide period into segments and find biggest moves
  const segments = Math.min(8, Math.floor(data.length / 5));
  const size = Math.floor(data.length / segments);
  const candidates: Move[] = [];

  for (let i = 0; i < segments; i++) {
    const from = data[i * size];
    const to   = data[Math.min((i + 1) * size, data.length - 1)];
    const pct  = ((to.price - from.price) / from.price) * 100;
    if (Math.abs(pct) >= 4) {
      candidates.push({ startDate: from.date, endDate: to.date, startPrice: from.price, endPrice: to.price, pct });
    }
  }

  return candidates
    .sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct))
    .slice(0, 4);
}

function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-KE", { day: "numeric", month: "short", year: "numeric" });
}

function fmtKES(v: number) {
  return `KES ${v.toFixed(2)}`;
}

function sign(n: number) { return n >= 0 ? "+" : ""; }

function describeRSI(rsi: number | null): string {
  if (rsi === null) return "";
  if (rsi > 70) return `RSI is **${rsi.toFixed(1)}** — above 70, which traders call "overbought." This means the stock has risen quickly and may be due for a pause or pullback, though it can stay elevated during strong trends.`;
  if (rsi < 30) return `RSI is **${rsi.toFixed(1)}** — below 30, which traders call "oversold." This suggests the stock has fallen sharply and a bounce is possible, though it can stay low in a sustained downtrend.`;
  return `RSI is **${rsi.toFixed(1)}** — in the neutral zone (30–70), meaning price momentum is balanced with no extreme buying or selling pressure.`;
}

function describeSMAPosition(price: number | null, sma20: number | null, sma50: number | null, sma200: number | null): string {
  if (!price) return "";
  const parts: string[] = [];
  if (sma20) {
    const d = ((price - sma20) / sma20) * 100;
    parts.push(`**${Math.abs(d).toFixed(1)}% ${d >= 0 ? "above" : "below"}** the 20-day average (SMA20 = ${fmtKES(sma20)})`);
  }
  if (sma50) {
    const d = ((price - sma50) / sma50) * 100;
    parts.push(`**${Math.abs(d).toFixed(1)}% ${d >= 0 ? "above" : "below"}** the 50-day average (SMA50 = ${fmtKES(sma50)})`);
  }
  if (sma200) {
    const d = ((price - sma200) / sma200) * 100;
    parts.push(`**${Math.abs(d).toFixed(1)}% ${d >= 0 ? "above" : "below"}** the 200-day average (SMA200 = ${fmtKES(sma200)})`);
  }
  if (!parts.length) return "";
  return `Current price is ${parts.join(", ")}. Moving averages act as dynamic support and resistance levels — being above them is generally considered bullish.`;
}

function describeMACd(macd: number | null, hist: number | null): string {
  if (macd === null) return "";
  const direction = (hist ?? macd) >= 0 ? "positive" : "negative";
  const trend     = (hist ?? macd) >= 0 ? "upward" : "downward";
  return `MACD histogram is **${direction}** (${(hist ?? macd).toFixed(3)}), suggesting short-term **${trend} momentum**. MACD measures the gap between two moving averages — when it turns positive, it often signals that short-term buying pressure is exceeding selling pressure.`;
}

function describeVolatility(vol: number | null): string {
  if (vol === null) return "";
  const level = vol > 3 ? "high" : vol > 1.5 ? "moderate" : "low";
  return `30-day volatility is **${vol.toFixed(2)}%** per day — ${level} for an NSE-listed stock. Higher volatility means the stock moves more sharply in both directions, which can amplify both gains and losses.`;
}

// ── Event matching ─────────────────────────────────────────────────────────────
function findNearbyEvent(events: CorporateEvent[], dateStr: string, windowDays = 21): CorporateEvent | null {
  const target = new Date(dateStr + "T00:00:00").getTime();
  const window = windowDays * 24 * 60 * 60 * 1000;
  for (const ev of events) {
    const evTime = new Date(ev.date + "T00:00:00").getTime();
    if (Math.abs(evTime - target) <= window) return ev;
  }
  return null;
}

const EVENT_TYPE_LABEL: Record<CorporateEvent["type"], string> = {
  earnings: "Earnings Release",
  dividend: "Dividend Announcement",
  rights_issue: "Rights Issue / Capital Raise",
  expansion: "Business Expansion",
  management: "Management Change",
  regulatory: "Regulatory Decision",
  restructuring: "Restructuring",
  other: "Corporate Event",
};

// ── Main generator ─────────────────────────────────────────────────────────────
function generateExplanation(
  company: CompanyDoc,
  data: PricePoint[],
  technicals: TechnicalsDoc | null | undefined,
  rangeLabel: string,
  events: CorporateEvent[]
): string {
  if (data.length < 2) return "";

  const startPrice  = data[0].price;
  const endPrice    = data[data.length - 1].price;
  const prices      = data.map((p) => p.price);
  const high        = Math.max(...prices);
  const low         = Math.min(...prices);
  const highDate    = data[prices.indexOf(high)].date;
  const lowDate     = data[prices.indexOf(low)].date;
  const totalPct    = ((endPrice - startPrice) / startPrice) * 100;
  const direction   = totalPct >= 0 ? "gained" : "lost";
  const moves       = findSignificantMoves(data);
  const sectorNote  = SECTOR_NOTES[company.sector] ?? "";

  const lines: string[] = [];

  // About This Company
  if (company.description) {
    lines.push("### About This Company");
    lines.push(company.description);
    lines.push("");
  }

  // Summary
  lines.push(`## ${company.name} · ${rangeLabel} Analysis`);
  lines.push(`**${fmtDate(data[0].date)} → ${fmtDate(data[data.length - 1].date)} · ${data.length} trading days**`);
  lines.push("");
  lines.push("### Summary");
  lines.push(
    `Over the ${rangeLabel} period, **${company.name} (${company.ticker})** ${direction} **${sign(totalPct)}${totalPct.toFixed(2)}%** — moving from ${fmtKES(startPrice)} to ${fmtKES(endPrice)}. ` +
    `The highest price in the window was ${fmtKES(high)} (${fmtDate(highDate)}) and the lowest was ${fmtKES(low)} (${fmtDate(lowDate)}), ` +
    `giving a peak-to-trough range of ${(((high - low) / low) * 100).toFixed(1)}%.`
  );

  // Key movements
  if (moves.length > 0) {
    lines.push("");
    lines.push("### Key Price Movements");
    const usedEventDates = new Set<string>();
    for (const m of moves) {
      const verb = m.pct >= 0 ? "rose" : "fell";
      const nearEvent = findNearbyEvent(events, m.startDate) ?? findNearbyEvent(events, m.endDate);
      let moveLine = `- **${fmtDate(m.startDate)} → ${fmtDate(m.endDate)}:** Price ${verb} **${sign(m.pct)}${m.pct.toFixed(1)}%** from ${fmtKES(m.startPrice)} to ${fmtKES(m.endPrice)}.`;
      if (nearEvent && !usedEventDates.has(nearEvent.date)) {
        usedEventDates.add(nearEvent.date);
        moveLine += ` This move coincides with a **${EVENT_TYPE_LABEL[nearEvent.type]}** on ${fmtDate(nearEvent.date)}: ${nearEvent.summary}`;
      }
      lines.push(moveLine);
    }
    if (events.length === 0) {
      lines.push(
        "- Note: No corporate event data is available for this company. Dividend payments, earnings releases, and macroeconomic announcements often explain sudden moves."
      );
    }
  }

  // Corporate events in range (even if no significant move matched)
  const rangeStart = data[0].date;
  const rangeEnd   = data[data.length - 1].date;
  const eventsInRange = events.filter((ev) => ev.date >= rangeStart && ev.date <= rangeEnd);
  if (eventsInRange.length > 0) {
    lines.push("");
    lines.push("### Corporate Events in This Period");
    for (const ev of eventsInRange) {
      lines.push(`- **${fmtDate(ev.date)} · ${EVENT_TYPE_LABEL[ev.type]}:** ${ev.title} — ${ev.summary}`);
    }
  }

  // Technical snapshot
  const rsiLine    = technicals ? describeRSI(technicals.rsi_14) : "";
  const smaLine    = technicals ? describeSMAPosition(endPrice, technicals.sma_20, technicals.sma_50, technicals.sma_200) : "";
  const macdLine   = technicals ? describeMACd(technicals.macd, technicals.macd_hist) : "";
  const volLine    = technicals ? describeVolatility(technicals.volatility_30d) : "";

  if (rsiLine || smaLine || macdLine || volLine) {
    lines.push("");
    lines.push("### Technical Snapshot");
    if (rsiLine)  lines.push(`- ${rsiLine}`);
    if (smaLine)  lines.push(`- ${smaLine}`);
    if (macdLine) lines.push(`- ${macdLine}`);
    if (volLine)  lines.push(`- ${volLine}`);
  }

  // Sector context
  if (sectorNote) {
    lines.push("");
    lines.push("### Sector Context");
    lines.push(sectorNote);
  }

  // Educational takeaways
  lines.push("");
  lines.push("### What This Teaches");
  if (Math.abs(totalPct) > 20) {
    lines.push(
      `- A **${Math.abs(totalPct).toFixed(0)}% move** in one period is substantial. Large moves often reflect a re-rating of the company's prospects — not just day-to-day trading noise. They often coincide with earnings results, analyst upgrades, or sector news.`
    );
  }
  if (technicals?.rsi_14 && technicals.rsi_14 > 65) {
    lines.push("- A high RSI after a strong run does not guarantee a reversal — it signals caution, not certainty. Strong trends can keep RSI elevated for extended periods.");
  }
  if (technicals?.sma_200 && endPrice > technicals.sma_200) {
    lines.push("- Trading above the 200-day average is widely seen as a long-term bullish sign. Many institutional investors use this as a basic filter before buying.");
  }
  lines.push(
    "- **Correlation is not causation** — price charts show *what* happened, not always *why*. Always combine chart reading with fundamental research (financial results, business news) for a complete picture."
  );

  // Disclaimer
  lines.push("");
  lines.push("### Limitations & Disclaimer");
  lines.push(
    "This is an automatically generated educational explanation based on historical price and technical indicator data only. It does not constitute investment advice and should not be the sole basis for any investment decision. It does not account for qualitative factors, company fundamentals, corporate events, or macroeconomic conditions not reflected in the price series. Past price behaviour does not predict future performance."
  );

  return lines.join("\n");
}

// ── Markdown renderer ──────────────────────────────────────────────────────────
function inlineBold(text: string): (string | JSX.Element)[] {
  return text.split(/(\*\*[^*]+\*\*)/).map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i} className="font-semibold text-ink">{p.slice(2, -2)}</strong>
      : p
  );
}

function MdLine({ line, idx }: { line: string; idx: number }) {
  if (line.startsWith("## "))
    return <h2 className="mt-4 mb-1 text-sm font-bold text-ink">{line.slice(3)}</h2>;
  if (line.startsWith("### "))
    return <h3 className="mt-3 mb-0.5 text-[10px] font-bold uppercase tracking-wider text-muted">{line.slice(4)}</h3>;
  if (line.startsWith("- "))
    return (
      <li className="ml-1 flex items-start gap-2 text-sm text-sub">
        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
        <span className="leading-relaxed">{inlineBold(line.slice(2))}</span>
      </li>
    );
  if (line.trim() === "") return <div className="h-1.5" />;
  return <p className="text-sm leading-relaxed text-sub">{inlineBold(line)}</p>;
}

// ── Component ──────────────────────────────────────────────────────────────────
interface Props {
  company: CompanyDoc;
  visible: PricePoint[];
  technicals: TechnicalsDoc | null | undefined;
  rangeLabel: string;
  events: CorporateEvent[];
}

export const PriceExplainer: FC<Props> = ({ company, visible, technicals, rangeLabel, events }) => {
  const [open, setOpen] = useState(false);

  const explanation = useMemo(
    () => generateExplanation(company, visible, technicals, rangeLabel, events),
    [company, visible, technicals, rangeLabel, events]
  );

  if (!explanation) return null;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-accent">✦</span>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">Price Analysis</p>
          </div>
          <p className="mt-0.5 text-[11px] text-hint">
            Educational breakdown · {rangeLabel} · updates with range selection
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 rounded-lg border border-rim bg-raised px-4 py-2 text-xs font-semibold text-sub transition-colors hover:border-accent hover:text-accent"
        >
          {open ? "Hide" : "Show Analysis"}
        </button>
      </div>

      {open && (
        <div className="mt-4 rounded-lg border border-seam bg-raised/40 px-4 py-3 space-y-0.5">
          {explanation.split("\n").map((line, i) => (
            <MdLine key={i} line={line} idx={i} />
          ))}
        </div>
      )}
    </div>
  );
};
