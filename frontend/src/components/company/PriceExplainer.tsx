import type { FC, JSX } from "react";
import { useMemo, useState } from "react";
import type {
  CompanyDoc,
  TechnicalsDoc,
  PricePoint,
  CorporateEvent,
  FinancialsDoc,
  MacroDoc,
} from "../../types/index";

// ── Sector context ─────────────────────────────────────────────────────────────
const SECTOR_NOTES: Record<string, string> = {
  Banking:
    "Banks profit from the net interest margin — the gap between lending and deposit rates. CBK rate hikes typically widen bank margins and boost profitability. Watch NPL ratios and loan book growth as the key fundamental signals.",
  "Telecommunication and Technology":
    "Telcos earn from voice, data, and mobile-money. ARPU growth and subscriber retention drive valuation. Government spectrum policy and M-Pesa-style fintech expansion are sector-specific macro catalysts.",
  "Energy and Petroleum":
    "Energy stocks track global crude and local fuel demand. Government pricing controls compress downstream margins when oil rises. KES depreciation raises import costs, squeezing margins further for petroleum distributors.",
  "Manufacturing and Allied":
    "Manufacturing margins are squeezed by input costs — energy, raw materials, imported components. A weaker KES makes imports more expensive. Strong consumer demand and export contracts are positive signals.",
  Insurance:
    "Insurers earn premium income and invest the float. Rising interest rates increase investment returns, boosting profitability. Claims ratios and regulatory capital buffers are the key risk metrics.",
  "Commercial and Services":
    "Commercial companies are sensitive to consumer confidence. Economic slowdowns hurt them first; recoveries lift them early. Discretionary spending tracks closely with real income growth.",
  "Real Estate Investment Trust":
    "REITs are valued like bonds — they become more attractive when interest rates fall. Occupancy rates, rental yields, and real estate capital values are the core metrics.",
  Agricultural:
    "Agricultural stocks are highly seasonal and sensitive to rainfall, global commodity prices, and harvest cycles. A poor growing season or falling commodity prices quickly compress margins.",
  Investment:
    "Investment holding companies are valued at a discount or premium to NAV — the sum of their portfolio. Understanding the underlying assets is essential to interpreting price moves.",
};

const SECTOR_MACRO_SENSITIVITY: Record<string, string> = {
  Banking: "rate-sensitive — benefits from CBK hikes",
  "Telecommunication and Technology": "defensive — resilient to rate cycles",
  "Energy and Petroleum": "oil-price and KES-sensitive",
  "Manufacturing and Allied": "cost-sensitive — hurt by KES depreciation and rate hikes",
  Insurance: "rate-sensitive — benefits from higher yields",
  "Commercial and Services": "consumer-sensitive — tracks GDP growth",
  "Real Estate Investment Trust": "rate-sensitive — benefits from rate cuts",
  Agricultural: "commodity and weather-sensitive",
  Investment: "NAV-driven — tracks underlying holdings",
};

// ── Types ──────────────────────────────────────────────────────────────────────
interface Move {
  startDate: string;
  endDate: string;
  startPrice: number;
  endPrice: number;
  pct: number;
}

interface TimelineItem {
  date: string;
  category: "earnings" | "dividend" | "event" | "cbk" | "corporate_action";
  driverTag: "(earnings)" | "(event)" | "(macro)" | "(price)";
  label: string;
  detail: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function fmtDate(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-KE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function fmtKES(v: number) {
  return `KES ${v.toFixed(2)}`;
}

function sign(n: number) {
  return n >= 0 ? "+" : "";
}

function yearOf(dateStr: string) {
  return dateStr.slice(0, 4);
}

const EVENT_LABEL: Record<CorporateEvent["type"], string> = {
  earnings: "Earnings Release",
  dividend: "Dividend Announcement",
  rights_issue: "Rights Issue / Capital Raise",
  expansion: "Business Expansion",
  management: "Management Change",
  regulatory: "Regulatory Decision",
  restructuring: "Restructuring",
  other: "Corporate Event",
};

function findSignificantMoves(data: PricePoint[], threshold = 4): Move[] {
  if (data.length < 10) return [];
  const segments = Math.min(8, Math.floor(data.length / 5));
  const size = Math.floor(data.length / segments);
  const candidates: Move[] = [];
  for (let i = 0; i < segments; i++) {
    const from = data[i * size];
    const to = data[Math.min((i + 1) * size, data.length - 1)];
    const pct = ((to.price - from.price) / from.price) * 100;
    if (Math.abs(pct) >= threshold) {
      candidates.push({
        startDate: from.date,
        endDate: to.date,
        startPrice: from.price,
        endPrice: to.price,
        pct,
      });
    }
  }
  return candidates.sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct)).slice(0, 5);
}

function nearestTimelineItem(
  items: TimelineItem[],
  dateStr: string,
  windowDays = 21
): TimelineItem | null {
  const target = new Date(dateStr + "T00:00:00").getTime();
  const windowMs = windowDays * 24 * 60 * 60 * 1000;
  let best: TimelineItem | null = null;
  let bestDist = Infinity;
  for (const item of items) {
    const d = Math.abs(new Date(item.date + "T00:00:00").getTime() - target);
    if (d <= windowMs && d < bestDist) {
      bestDist = d;
      best = item;
    }
  }
  return best;
}

// ── Timeline builder ───────────────────────────────────────────────────────────
function buildTimeline(
  rangeStart: string,
  rangeEnd: string,
  events: CorporateEvent[],
  financials: FinancialsDoc | null | undefined,
  macro: MacroDoc | null | undefined
): TimelineItem[] {
  const items: TimelineItem[] = [];

  for (const ev of events) {
    if (ev.date >= rangeStart && ev.date <= rangeEnd) {
      items.push({
        date: ev.date,
        category: "event",
        driverTag: "(event)",
        label: EVENT_LABEL[ev.type],
        detail: `${ev.title} — ${ev.summary}`,
      });
    }
  }

  if (financials?.annual) {
    for (const r of financials.annual) {
      const date = r.announcement_date;
      if (date >= rangeStart && date <= rangeEnd) {
        const parts: string[] = [];
        if (r.revenue_kes_mn !== null) parts.push(`Revenue KES ${(r.revenue_kes_mn / 1000).toFixed(1)}bn`);
        if (r.net_income_kes_mn !== null) parts.push(`PAT KES ${(r.net_income_kes_mn / 1000).toFixed(1)}bn`);
        if (r.eps !== null) parts.push(`EPS KES ${r.eps.toFixed(2)}`);
        if (r.bvps !== null) parts.push(`BVPS KES ${r.bvps.toFixed(2)}`);
        items.push({
          date,
          category: "earnings",
          driverTag: "(earnings)",
          label: `Earnings — ${r.period} (${r.period_type === "annual" ? "Full Year" : "Interim"})`,
          detail: parts.length ? parts.join(", ") : r.notes ?? "Results published",
        });
      }
    }
  }

  if (financials?.dividends) {
    for (const div of financials.dividends) {
      const date = div.announcement_date;
      if (date >= rangeStart && date <= rangeEnd && div.type !== "none") {
        const exDate = div.ex_date ? `, ex-date ${fmtDate(div.ex_date)}` : "";
        items.push({
          date,
          category: "dividend",
          driverTag: "(event)",
          label: `Dividend (${div.type}) — KES ${div.amount_kes.toFixed(2)}/share`,
          detail: `Dividend of KES ${div.amount_kes.toFixed(2)} per share${exDate}${div.notes ? `. ${div.notes}` : ""}`,
        });
      }
    }
  }

  if (financials?.corporate_actions) {
    for (const ca of financials.corporate_actions) {
      if (ca.date >= rangeStart && ca.date <= rangeEnd) {
        items.push({
          date: ca.date,
          category: "corporate_action",
          driverTag: "(event)",
          label: ca.type,
          detail: ca.title ?? ca.details,
        });
      }
    }
  }

  if (financials?.announcements) {
    for (const ann of financials.announcements) {
      if (ann.date >= rangeStart && ann.date <= rangeEnd) {
        const category: TimelineItem["category"] =
          ann.type === "financial_result" ? "earnings"
          : ann.type === "dividend" ? "dividend"
          : "corporate_action";
        const driverTag: TimelineItem["driverTag"] =
          ann.type === "financial_result" ? "(earnings)" : "(event)";
        const label =
          ann.type === "financial_result" ? "Results Filing (NSE)"
          : ann.type === "dividend" ? "Dividend Notice (NSE)"
          : ann.type === "agm" ? "AGM Notice (NSE)"
          : "Corporate Action Filing (NSE)";
        items.push({
          date: ann.date,
          category,
          driverTag,
          label,
          detail: ann.title
            .replace(/&#8211;/g, "–")
            .replace(/&#8212;/g, "—")
            .replace(/&amp;/g, "&")
            .replace(/&#8217;/g, "'")
            .replace(/&#8216;/g, "'"),
        });
      }
    }
  }

  if (macro?.cbk_rates) {
    for (const cbk of macro.cbk_rates) {
      if (cbk.date >= rangeStart && cbk.date <= rangeEnd) {
        const action =
          cbk.decision === "hike"
            ? `hiked by ${cbk.change_bps}bps to **${cbk.rate}%**`
            : cbk.decision === "cut"
            ? `cut by ${Math.abs(cbk.change_bps)}bps to **${cbk.rate}%**`
            : `held at **${cbk.rate}%**`;
        items.push({
          date: cbk.date,
          category: "cbk",
          driverTag: "(macro)",
          label: `CBK Rate ${cbk.decision === "hold" ? "Hold" : cbk.decision === "hike" ? "Hike" : "Cut"} → ${cbk.rate}%`,
          detail: `Central Bank of Kenya ${action}${cbk.notes ? `. ${cbk.notes}` : ""}`,
        });
      }
    }
  }

  return items.sort((a, b) => a.date.localeCompare(b.date));
}

// ── CBK context helpers ────────────────────────────────────────────────────────
function cbkRateAt(macro: MacroDoc | null | undefined, dateStr: string): number | null {
  if (!macro?.cbk_rates?.length) return null;
  const sorted = [...macro.cbk_rates].sort((a, b) => a.date.localeCompare(b.date));
  let last: number | null = null;
  for (const r of sorted) {
    if (r.date <= dateStr) last = r.rate;
  }
  return last;
}

function inflationAt(macro: MacroDoc | null | undefined, year: string): number | null {
  return macro?.annual_inflation?.[year] ?? null;
}

function kesUsdAt(macro: MacroDoc | null | undefined, year: string): number | null {
  return macro?.kes_usd_year_end?.[year] ?? null;
}

// ── RSI / technical descriptions ──────────────────────────────────────────────
function describeRSI(rsi: number | null): string {
  if (rsi === null) return "";
  if (rsi > 70)
    return `RSI **${rsi.toFixed(1)}** — overbought territory. The stock has risen quickly and may consolidate, though strong trends can sustain elevated RSI.`;
  if (rsi < 30)
    return `RSI **${rsi.toFixed(1)}** — oversold territory. The stock has declined sharply; a technical bounce is possible but not guaranteed.`;
  return `RSI **${rsi.toFixed(1)}** — neutral zone (30–70), indicating balanced momentum with no extreme buying or selling pressure.`;
}

function describeSMA(price: number, sma20: number | null, sma50: number | null, sma200: number | null): string {
  const parts: string[] = [];
  if (sma20) {
    const d = ((price - sma20) / sma20) * 100;
    parts.push(`**${Math.abs(d).toFixed(1)}% ${d >= 0 ? "above" : "below"}** the 20-day SMA (${fmtKES(sma20)})`);
  }
  if (sma50) {
    const d = ((price - sma50) / sma50) * 100;
    parts.push(`**${Math.abs(d).toFixed(1)}% ${d >= 0 ? "above" : "below"}** the 50-day SMA (${fmtKES(sma50)})`);
  }
  if (sma200) {
    const d = ((price - sma200) / sma200) * 100;
    parts.push(`**${Math.abs(d).toFixed(1)}% ${d >= 0 ? "above" : "below"}** the 200-day SMA (${fmtKES(sma200)})`);
  }
  return parts.join(", ");
}

// ── Main generator ─────────────────────────────────────────────────────────────
function generateExplanation(
  company: CompanyDoc,
  data: PricePoint[],
  technicals: TechnicalsDoc | null | undefined,
  rangeLabel: string,
  events: CorporateEvent[],
  financials: FinancialsDoc | null | undefined,
  macro: MacroDoc | null | undefined
): string {
  if (data.length < 2) return "";

  const startPrice = data[0].price;
  const endPrice = data[data.length - 1].price;
  const prices = data.map((p) => p.price);
  const high = Math.max(...prices);
  const low = Math.min(...prices);
  const highDate = data[prices.indexOf(high)].date;
  const lowDate = data[prices.indexOf(low)].date;
  const totalPct = ((endPrice - startPrice) / startPrice) * 100;
  const direction = totalPct >= 0 ? "gained" : "lost";
  const rangeStart = data[0].date;
  const rangeEnd = data[data.length - 1].date;
  const startYear = yearOf(rangeStart);
  const endYear = yearOf(rangeEnd);

  const timeline = buildTimeline(rangeStart, rangeEnd, events, financials, macro);
  const moves = findSignificantMoves(data);
  const sectorNote = SECTOR_NOTES[company.sector] ?? "";
  const sectorSensitivity = SECTOR_MACRO_SENSITIVITY[company.sector] ?? "";

  const cbkStart = cbkRateAt(macro, rangeStart);
  const cbkEnd = cbkRateAt(macro, rangeEnd);
  const inflStart = inflationAt(macro, startYear);
  const inflEnd = inflationAt(macro, endYear);
  const kesStart = kesUsdAt(macro, startYear);
  const kesEnd = kesUsdAt(macro, endYear);

  const lines: string[] = [];

  // ── Section header ──────────────────────────────────────────────────────────
  lines.push(`## ${company.name} · ${rangeLabel} Price Analysis`);
  lines.push(`**${fmtDate(rangeStart)} → ${fmtDate(rangeEnd)} · ${data.length} trading days**`);
  lines.push("");

  // ── Section 1: Summary ──────────────────────────────────────────────────────
  lines.push("### 1. Summary");
  lines.push(
    `**${company.name} (${company.ticker})** ${direction} **${sign(totalPct)}${totalPct.toFixed(2)}%** over the ${rangeLabel} period — ` +
    `from ${fmtKES(startPrice)} to ${fmtKES(endPrice)}.`
  );
  lines.push(
    `- **Period high:** ${fmtKES(high)} on ${fmtDate(highDate)} | **Period low:** ${fmtKES(low)} on ${fmtDate(lowDate)}` +
    ` | **Peak-to-trough range:** ${(((high - low) / low) * 100).toFixed(1)}%`
  );

  const macroSummaryParts: string[] = [];
  if (cbkStart !== null && cbkEnd !== null) {
    if (cbkStart !== cbkEnd) {
      macroSummaryParts.push(
        `CBK benchmark rate moved from **${cbkStart}%** to **${cbkEnd}%** over this period`
      );
    } else {
      macroSummaryParts.push(`CBK benchmark rate was stable at **${cbkStart}%**`);
    }
  }
  if (inflEnd !== null) {
    macroSummaryParts.push(`annual inflation was **${inflEnd}%** in ${endYear}`);
  }
  if (kesStart !== null && kesEnd !== null && startYear !== endYear) {
    const kes_chg = ((kesEnd - kesStart) / kesStart) * 100;
    macroSummaryParts.push(
      `KES/USD moved from **${kesStart}** to **${kesEnd}** (${sign(kes_chg)}${kes_chg.toFixed(1)}% ${kes_chg > 0 ? "depreciation" : "appreciation"})`
    );
  } else if (kesEnd !== null) {
    macroSummaryParts.push(`KES/USD closed ${endYear} at **${kesEnd}**`);
  }
  if (macroSummaryParts.length > 0) {
    lines.push(`- **Macro backdrop:** ${macroSummaryParts.join("; ")}.`);
  }

  if (company.sector) {
    lines.push(`- **Sector:** ${company.sector}${sectorSensitivity ? ` — ${sectorSensitivity}` : ""}.`);
  }
  if (timeline.length > 0) {
    const earnings = timeline.filter((t) => t.category === "earnings").length;
    const divs = timeline.filter((t) => t.category === "dividend").length;
    const cbkEvents = timeline.filter((t) => t.category === "cbk").length;
    const corpEvents = timeline.filter((t) => t.category === "event" || t.category === "corporate_action").length;
    const parts: string[] = [];
    if (earnings > 0) parts.push(`${earnings} earnings release${earnings > 1 ? "s" : ""}`);
    if (divs > 0) parts.push(`${divs} dividend announcement${divs > 1 ? "s" : ""}`);
    if (corpEvents > 0) parts.push(`${corpEvents} corporate event${corpEvents > 1 ? "s" : ""}`);
    if (cbkEvents > 0) parts.push(`${cbkEvents} CBK rate decision${cbkEvents > 1 ? "s" : ""}`);
    lines.push(`- **Documented events in period:** ${parts.join(", ")}.`);
  } else {
    lines.push(`- **Documented events:** No data-confirmed events found for this period. Price moves are classified as unexplained or contextual.`);
  }
  lines.push("");

  // ── Section 2: Timeline of Key Events ──────────────────────────────────────
  lines.push("### 2. Timeline of Key Events");
  if (timeline.length === 0) {
    lines.push("No confirmed corporate, financial, or macro events found within this period.");
  } else {
    for (const item of timeline) {
      lines.push(`- **${fmtDate(item.date)} ${item.driverTag}** · **${item.label}:** ${item.detail}`);
    }
  }
  lines.push("");

  // ── Section 3: Data-Confirmed Drivers ──────────────────────────────────────
  lines.push("### 3. Data-Confirmed Drivers");

  if (moves.length === 0) {
    lines.push("No price moves large enough to classify as significant during this period (threshold: 4%).");
  } else {
    const usedDates = new Set<string>();
    for (const m of moves) {
      const verb = m.pct >= 0 ? "rose" : "fell";
      const matched = nearestTimelineItem(timeline, m.startDate) ?? nearestTimelineItem(timeline, m.endDate);
      let confidence: string;
      let driverTag: string;
      let explanation: string;

      if (matched && !usedDates.has(matched.date)) {
        usedDates.add(matched.date);
        confidence = "data-confirmed";
        driverTag = matched.driverTag;
        explanation = `Coincides with **${matched.label}** on ${fmtDate(matched.date)}: ${matched.detail}`;
      } else if (macro?.cbk_rates?.some((r) => r.date >= m.startDate && r.date <= m.endDate)) {
        confidence = "likely-contextual";
        driverTag = "(macro)";
        const cbkInWindow = macro.cbk_rates.find(
          (r) => r.date >= m.startDate && r.date <= m.endDate
        );
        explanation = cbkInWindow
          ? `CBK rate ${cbkInWindow.decision} to ${cbkInWindow.rate}% during this window may have shifted investor sentiment toward ${company.sector} stocks.`
          : `Macro conditions during this period may have influenced sector-wide sentiment.`;
      } else if (timeline.length > 0) {
        confidence = "likely-contextual";
        driverTag = "(price)";
        explanation = `No specific event found within 21 days. The move may reflect broader sector rotation, liquidity changes, or reaction to the prior timeline event.`;
      } else {
        confidence = "unexplained";
        driverTag = "(price)";
        explanation = `No corporate, financial, or macro event identified as a driver. The move may reflect thin liquidity, broader market sentiment, or undocumented developments.`;
      }

      lines.push(
        `- **${fmtDate(m.startDate)} → ${fmtDate(m.endDate)} ${driverTag}** [${confidence}]` +
        ` — Price ${verb} **${sign(m.pct)}${m.pct.toFixed(1)}%** from ${fmtKES(m.startPrice)} to ${fmtKES(m.endPrice)}. ${explanation}`
      );
    }
  }

  // Technical indicators as additional driver context
  if (technicals) {
    const endP = endPrice;
    const rsiStr = describeRSI(technicals.rsi_14);
    const smaStr = describeSMA(endP, technicals.sma_20, technicals.sma_50, technicals.sma_200);
    const histVal = technicals.macd_hist;

    if (rsiStr || smaStr || histVal !== null) {
      lines.push("");
      lines.push("**Technical read at period end (technical):**");
      if (rsiStr) lines.push(`- ${rsiStr}`);
      if (smaStr) lines.push(`- Current price is ${smaStr}.`);
      if (histVal !== null) {
        const macdDir = histVal >= 0 ? "positive" : "negative";
        lines.push(
          `- MACD histogram is **${macdDir}** (${histVal.toFixed(3)}), indicating short-term ${histVal >= 0 ? "upward" : "downward"} momentum.`
        );
      }
      if (technicals.volatility_30d !== null) {
        const vol = technicals.volatility_30d;
        const level = vol > 3 ? "high" : vol > 1.5 ? "moderate" : "low";
        lines.push(
          `- 30-day daily volatility is **${vol.toFixed(2)}%** — ${level} for NSE. Higher volatility amplifies both gains and losses.`
        );
      }
    }
  }
  lines.push("");

  // ── Section 4: Contextual / Macro Factors ──────────────────────────────────
  lines.push("### 4. Contextual & Macro Factors");

  const macroLines: string[] = [];

  if (macro?.cbk_rates) {
    const cbkInRange = macro.cbk_rates
      .filter((r) => r.date >= rangeStart && r.date <= rangeEnd)
      .sort((a, b) => a.date.localeCompare(b.date));

    if (cbkInRange.length > 0) {
      const hikes = cbkInRange.filter((r) => r.decision === "hike").length;
      const cuts = cbkInRange.filter((r) => r.decision === "cut").length;
      const holds = cbkInRange.filter((r) => r.decision === "hold").length;
      const startRate = cbkStart;
      const endRate = cbkEnd;
      let cbkNarrative = "";
      if (hikes > cuts) {
        cbkNarrative = `CBK was in **tightening mode** during this period (${hikes} hike${hikes > 1 ? "s" : ""}, ${holds} hold${holds !== 1 ? "s" : ""}${cuts > 0 ? `, ${cuts} cut${cuts > 1 ? "s" : ""}` : ""})`;
        if (startRate !== null && endRate !== null) cbkNarrative += `, with the rate rising from ${startRate}% to ${endRate}%`;
      } else if (cuts > hikes) {
        cbkNarrative = `CBK was in **easing mode** (${cuts} cut${cuts > 1 ? "s" : ""}, ${holds} hold${holds !== 1 ? "s" : ""}${hikes > 0 ? `, ${hikes} hike${hikes > 1 ? "s" : ""}` : ""})`;
        if (startRate !== null && endRate !== null) cbkNarrative += `, with the rate falling from ${startRate}% to ${endRate}%`;
      } else {
        cbkNarrative = `CBK held rates steady at ${startRate ?? endRate ?? "?"}% through most of this period`;
      }
      macroLines.push(`- **Interest rates (macro):** ${cbkNarrative}. ${sectorSensitivity ? `For ${company.sector} stocks (${sectorSensitivity}), this typically implies ${hikes > cuts ? "margin expansion for lenders, higher borrowing costs for leveraged companies" : "cheaper credit, rising asset valuations, and potential re-rating for rate-sensitive sectors"}.` : ""}`);
    } else if (cbkStart !== null) {
      macroLines.push(`- **Interest rates (macro):** CBK rate was **${cbkStart}%** at the start of this period — no policy changes recorded within the window.`);
    }
  }

  if (inflStart !== null || inflEnd !== null) {
    if (startYear === endYear && inflEnd !== null) {
      const level = inflEnd > 7 ? "elevated" : inflEnd > 4 ? "moderate" : "contained";
      macroLines.push(
        `- **Inflation (macro):** Annual inflation was **${inflEnd}%** in ${endYear} — ${level}. ${inflEnd > 7 ? "High inflation erodes real returns and can pressure consumer stocks." : inflEnd < 4 ? "Low inflation supports real purchasing power and often accompanies accommodative monetary policy." : "Moderate inflation has mixed effects across sectors."}`
      );
    } else if (inflStart !== null && inflEnd !== null) {
      const dir = inflEnd > inflStart ? "rose" : "fell";
      macroLines.push(
        `- **Inflation (macro):** Annual inflation ${dir} from **${inflStart}%** (${startYear}) to **${inflEnd}%** (${endYear}).`
      );
    }
  }

  if (kesStart !== null || kesEnd !== null) {
    if (startYear !== endYear && kesStart !== null && kesEnd !== null) {
      const change = ((kesEnd - kesStart) / kesStart) * 100;
      const dir = change > 0 ? "depreciated" : "appreciated";
      macroLines.push(
        `- **KES/USD (macro):** The Kenyan shilling ${dir} from **${kesStart}** to **${kesEnd}** (${sign(change)}${change.toFixed(1)}% over the period years). ${change > 5 ? "Significant shilling weakness raises import costs and can hurt import-dependent businesses." : change < -5 ? "KES appreciation reduces import costs and can boost consumer purchasing power." : "The exchange rate was broadly stable over this period."}`
      );
    } else if (kesEnd !== null) {
      macroLines.push(`- **KES/USD (macro):** KES/USD closed ${endYear} at **${kesEnd}**.`);
    }
  }

  if (macro?.nse20_year_end) {
    const nse20End = macro.nse20_year_end[endYear];
    const nse20Start = macro.nse20_year_end[startYear];
    if (nse20End && nse20Start && startYear !== endYear) {
      const nse20Chg = ((nse20End - nse20Start) / nse20Start) * 100;
      macroLines.push(
        `- **NSE20 context:** The NSE 20 Share Index moved from **${nse20Start.toLocaleString()}** to **${nse20End.toLocaleString()}** (${sign(nse20Chg)}${nse20Chg.toFixed(1)}%) over the same period years. ` +
        `${company.ticker} ${direction} **${sign(totalPct)}${totalPct.toFixed(1)}%** — ${Math.abs(totalPct) > Math.abs(nse20Chg) ? "outperforming" : "underperforming"} the index.`
      );
    }
  }

  if (sectorNote) {
    macroLines.push(`- **Sector dynamics (macro):** ${sectorNote}`);
  }

  if (macroLines.length === 0) {
    lines.push("No macro or contextual data available for this period.");
  } else {
    for (const l of macroLines) lines.push(l);
  }
  lines.push("");

  // ── Section 5: What This Teaches ───────────────────────────────────────────
  lines.push("### 5. What This Teaches");

  const teaches: string[] = [];

  if (Math.abs(totalPct) > 25) {
    teaches.push(
      `A **${Math.abs(totalPct).toFixed(0)}% move** over a single period is substantial by NSE standards. Moves of this magnitude typically reflect a fundamental re-rating — a change in earnings expectations, a major corporate event, or a significant macro shift — rather than noise. Understanding the specific catalyst matters more than the price move itself.`
    );
  } else if (Math.abs(totalPct) > 10) {
    teaches.push(
      `A **${Math.abs(totalPct).toFixed(0)}% move** is meaningful. On the NSE, where liquidity is lower than developed markets, moves of this scale often reflect real information — earnings surprises, dividend announcements, or sector re-ratings — rather than speculative noise.`
    );
  }

  const confirmedCount = moves.filter((m) => {
    const matched = nearestTimelineItem(timeline, m.startDate) ?? nearestTimelineItem(timeline, m.endDate);
    return !!matched;
  }).length;

  if (confirmedCount > 0 && moves.length > 0) {
    teaches.push(
      `**${confirmedCount} of ${moves.length} significant price moves** in this period coincide with documented events (earnings, dividends, corporate actions, or CBK decisions). This illustrates that NSE stock prices do respond to fundamental and macro catalysts — not just technical momentum.`
    );
  }

  if (timeline.some((t) => t.category === "earnings")) {
    teaches.push(
      `**Earnings releases** are among the highest-impact catalysts on the NSE. The market often "prices in" expectations before the release and moves sharply when actual results diverge from consensus. Tracking the direction of EPS and PAT growth across multiple periods reveals whether a company's profitability trend is intact.`
    );
  }

  if (timeline.some((t) => t.category === "dividend")) {
    teaches.push(
      `**Dividend announcements** tend to attract buyers before the ex-date and can trigger selling afterward (the "dividend capture" pattern). For income-focused investors common in Kenya's retail market, dividend yield often drives investment decisions more than capital appreciation.`
    );
  }

  if (timeline.some((t) => t.category === "cbk")) {
    teaches.push(
      `**CBK rate decisions** create sector-level moves, not just individual stock moves. Banking stocks tend to benefit from hikes; rate-sensitive sectors like REITs and utilities often weaken. Watching the MPC calendar and positioning before decisions is a common institutional strategy.`
    );
  }

  if (technicals?.rsi_14 && technicals.rsi_14 > 65) {
    teaches.push(
      `**High RSI after a strong run** does not guarantee a reversal — it signals momentum is extended. Strong trends can sustain elevated RSI for months. The risk is in position sizing, not necessarily in the direction.`
    );
  }

  if (technicals?.sma_200 && endPrice > technicals.sma_200) {
    teaches.push(
      `**Trading above the 200-day SMA** is widely interpreted as a long-term bullish signal by institutional investors. Many fund mandates require this as a basic entry filter. Losing this level — especially on high volume — can trigger systematic selling.`
    );
  }

  teaches.push(
    `**Chart patterns show what happened, not why.** Price history must be combined with fundamental research — earnings trends, balance sheet health, dividend sustainability, and competitive position — for investment-grade analysis.`
  );

  for (const t of teaches) lines.push(`- ${t}`);
  lines.push("");

  // ── Section 6: Limitations & Disclaimer ────────────────────────────────────
  lines.push("### 6. Limitations & Disclaimer");
  lines.push(
    `This is an automatically generated educational analysis based on historical price data, technical indicators, financial records, and macroeconomic data available in this platform's database. **It does not constitute investment advice** and should not be the sole basis for any investment decision.`
  );
  lines.push("");
  lines.push(
    `**Data limitations:** Financial and event data may be incomplete, delayed, or contain inaccuracies. NSE corporate disclosures are not always timely, and some historical events may not be captured. Event proximity matching (21-day window) is heuristic — correlation does not prove causation.`
  );
  lines.push("");
  lines.push(
    `**What this analysis cannot assess:** Management quality, competitive moats, governance risk, off-balance-sheet liabilities, undisclosed related-party transactions, or qualitative factors that professional analysts spend significant time evaluating. Past price behaviour does not predict future performance.`
  );

  return lines.join("\n");
}

// ── Markdown renderer ──────────────────────────────────────────────────────────
function inlineBold(text: string): (string | JSX.Element)[] {
  return text.split(/(\*\*[^*]+\*\*)/).map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? (
      <strong key={i} className="font-semibold text-ink">
        {p.slice(2, -2)}
      </strong>
    ) : (
      p
    )
  );
}

function MdLine({ line }: { line: string }) {
  if (line.startsWith("## "))
    return (
      <h2 className="mt-4 mb-1 text-sm font-bold text-ink">{line.slice(3)}</h2>
    );
  if (line.startsWith("### "))
    return (
      <h3 className="mt-3 mb-0.5 text-[10px] font-bold uppercase tracking-wider text-muted">
        {line.slice(4)}
      </h3>
    );
  if (line.startsWith("- "))
    return (
      <li className="ml-1 flex items-start gap-2 text-sm text-sub">
        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
        <span className="leading-relaxed">{inlineBold(line.slice(2))}</span>
      </li>
    );
  if (line.trim() === "") return <div className="h-1.5" />;
  return (
    <p className="text-sm leading-relaxed text-sub">{inlineBold(line)}</p>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────
interface Props {
  company: CompanyDoc;
  visible: PricePoint[];
  technicals: TechnicalsDoc | null | undefined;
  rangeLabel: string;
  events: CorporateEvent[];
  financials: FinancialsDoc | null | undefined;
  macro: MacroDoc | null | undefined;
}

export const PriceExplainer: FC<Props> = ({
  company,
  visible,
  technicals,
  rangeLabel,
  events,
  financials,
  macro,
}) => {
  const [open, setOpen] = useState(false);

  const explanation = useMemo(
    () =>
      generateExplanation(company, visible, technicals, rangeLabel, events, financials, macro),
    [company, visible, technicals, rangeLabel, events, financials, macro]
  );

  if (!explanation) return null;

  const hasFinancials = !!financials?.annual?.length || !!financials?.dividends?.length;
  const hasMacro = !!macro?.cbk_rates?.length;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-accent">✦</span>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">
              Deep Price Analysis
            </p>
          </div>
          <p className="mt-0.5 text-[11px] text-hint">
            6-section breakdown · {rangeLabel} · {hasFinancials ? "financials included" : "no financials"} · {hasMacro ? "macro included" : "no macro data"}
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
            <MdLine key={i} line={line} />
          ))}
        </div>
      )}
    </div>
  );
};
