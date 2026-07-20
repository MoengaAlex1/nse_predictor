import type { FC } from "react";
import { useState, useCallback } from "react";
import type { CompanyDoc, TechnicalsDoc, PricePoint } from "../../types/index";

// ── System prompt ──────────────────────────────────────────────────────────────
const SYSTEM_PROMPT = `SYSTEM ROLE:
You are a financial market educator writing for retail investors learning to read the Nairobi Securities Exchange (NSE). Your job is to explain WHY a listed company's share price moved the way it did over a given period, using only the data provided. You are teaching general stock-market literacy through a real example — you are not a licensed investment advisor and must never issue buy/sell/hold recommendations or price predictions.

TASK:
1. Identify the most significant price movements in the period (define "significant" as any move of 10%+ within a rolling 30-day window, plus the overall period return).
2. For each significant movement, look for data points (technical indicators, volume patterns, price structure) that fall within or shortly before that window.
3. Clearly separate findings into:
   a. "Data-confirmed drivers" — movements that closely align with a specific data point in the provided dataset.
   b. "Likely contributing context" — broader sector/macro trends that plausibly influenced the move but aren't directly evidenced.
   c. "Unexplained by available data" — movements where no corresponding data point exists; state this honestly rather than inventing a cause.
4. For each driver identified, add one or two sentences of general stock-market education explaining the underlying principle so the reader learns a transferable lesson, not just a fact about this one stock.
5. Note where correlation is being described, not proven causation.

OUTPUT FORMAT:
- Summary (2-3 sentences): overall direction and magnitude of the price move over the period.
- Timeline of Key Price Movements: dated list of major inflection points with brief observations.
- Data-Confirmed Drivers: short paragraphs citing specific numbers and dates from the data.
- Contextual Factors: what broader sector or macro conditions might apply to this company type.
- What This Teaches About Investing: 2-4 sentences of general educational takeaway a new NSE investor can apply to other stocks.
- Limitations & Disclaimer: one short paragraph stating this is an automatically generated educational explanation based on historical price data only, is not investment advice, may omit non-public or qualitative factors, and that past price behavior does not predict future performance.

STYLE CONSTRAINTS:
- Plain language suitable for a first-time retail investor; define any financial term on first use.
- No hype, no urgency language, no recommendation to buy/sell/hold.
- Every factual claim about a price move must reference a specific date and figure from the input data.
- If input data is insufficient to explain a move, say so explicitly instead of guessing.
- Keep the full response under 700 words.`;

// ── Prompt builder ─────────────────────────────────────────────────────────────
function buildPrompt(
  company: CompanyDoc,
  visible: PricePoint[],
  technicals: TechnicalsDoc | null | undefined,
  rangeLabel: string
): string {
  if (visible.length < 2) return "";

  const startPrice = visible[0].price;
  const endPrice   = visible[visible.length - 1].price;
  const prices     = visible.map((p) => p.price);
  const high       = Math.max(...prices);
  const low        = Math.min(...prices);
  const highIdx    = prices.indexOf(high);
  const lowIdx     = prices.indexOf(low);
  const pctChange  = (((endPrice - startPrice) / startPrice) * 100).toFixed(2);
  const sign       = Number(pctChange) >= 0 ? "+" : "";

  // Sample to ~60 points to keep context reasonable
  const step = Math.max(1, Math.floor(visible.length / 60));
  const sampled = visible.filter((_, i) => i % step === 0 || i === visible.length - 1);
  const priceJson = JSON.stringify(
    sampled.map((p) => ({ date: p.date, close: p.price.toFixed(2) }))
  );

  const techJson = technicals
    ? JSON.stringify({
        as_of: technicals.date,
        rsi_14: technicals.rsi_14,
        macd: technicals.macd,
        macd_hist: technicals.macd_hist,
        bb_upper: technicals.bb_upper,
        bb_lower: technicals.bb_lower,
        sma_20: technicals.sma_20,
        sma_50: technicals.sma_50,
        sma_200: technicals.sma_200,
        ema_12: technicals.ema_12,
        ema_26: technicals.ema_26,
        volatility_30d: technicals.volatility_30d,
        avg_volume_30d: technicals.avg_volume_30d,
        daily_return_pct: technicals.daily_return,
      })
    : "Not available.";

  return `Analyse the following NSE-listed company's share price for the ${rangeLabel} period:

COMPANY:
- Name: ${company.name}
- Ticker: ${company.ticker}
- Sector: ${company.sector}

PERIOD STATISTICS:
- Analysis window: ${visible[0].date} to ${visible[visible.length - 1].date} (${rangeLabel} · ${visible.length} trading days)
- Start price: KES ${startPrice.toFixed(2)} on ${visible[0].date}
- End price:   KES ${endPrice.toFixed(2)} on ${visible[visible.length - 1].date}
- Period high: KES ${high.toFixed(2)} on ${visible[highIdx].date}
- Period low:  KES ${low.toFixed(2)} on ${visible[lowIdx].date}
- Overall change: ${sign}${pctChange}%

PRICE DATA (${sampled.length} sampled points, KES close):
${priceJson}

TECHNICAL INDICATORS (end of period):
${techJson}

IMPORTANT — DATA GAPS:
Dividend history, rights issues, EPS/revenue results, M&A events, CBK policy changes, and sector news are not available in this dataset. For any section that requires that data, write "Insufficient data available" rather than speculating. Still provide full educational takeaways.`;
}

// ── Tiny markdown renderer ─────────────────────────────────────────────────────
function inlineBold(text: string): (string | JSX.Element)[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i} className="font-semibold text-ink">{p.slice(2, -2)}</strong>
      : p
  );
}

function MarkdownLine({ line, idx }: { line: string; idx: number }) {
  if (line.startsWith("### "))
    return <p key={idx} className="mt-3 text-[10px] font-bold uppercase tracking-wider text-muted">{line.slice(4)}</p>;
  if (line.startsWith("## "))
    return <h3 key={idx} className="mt-4 mb-0.5 text-sm font-bold text-ink">{line.slice(3)}</h3>;
  if (line.startsWith("# "))
    return <h2 key={idx} className="mt-4 mb-1 text-base font-bold text-ink">{line.slice(2)}</h2>;
  if (line.startsWith("- ") || line.startsWith("* "))
    return (
      <li key={idx} className="ml-1 flex items-start gap-2 text-sm text-sub">
        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
        <span>{inlineBold(line.slice(2))}</span>
      </li>
    );
  if (line.trim() === "") return <div key={idx} className="h-2" />;
  return <p key={idx} className="text-sm leading-relaxed text-sub">{inlineBold(line)}</p>;
}

function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-0.5">
      {lines.map((line, i) => <MarkdownLine key={i} line={line} idx={i} />)}
    </div>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────
interface Props {
  company: CompanyDoc;
  visible: PricePoint[];
  technicals: TechnicalsDoc | null | undefined;
  rangeLabel: string;
}

type Status = "idle" | "loading" | "streaming" | "done" | "error";

export const PriceExplainer: FC<Props> = ({ company, visible, technicals, rangeLabel }) => {
  const [status, setStatus]      = useState<Status>("idle");
  const [explanation, setExpl]   = useState("");
  const [errorMsg, setErrorMsg]  = useState("");

  const run = useCallback(async () => {
    const apiKey = (import.meta as any).env.VITE_ANTHROPIC_API_KEY as string | undefined;
    if (!apiKey) {
      setErrorMsg("Add VITE_ANTHROPIC_API_KEY to frontend/.env.local to enable AI analysis.");
      setStatus("error");
      return;
    }

    const prompt = buildPrompt(company, visible, technicals, rangeLabel);
    if (!prompt) return;

    setStatus("loading");
    setExpl("");
    setErrorMsg("");

    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
          "anthropic-dangerous-direct-browser-access": "true",
        },
        body: JSON.stringify({
          model: "claude-haiku-4-5-20251001",
          max_tokens: 1200,
          stream: true,
          system: SYSTEM_PROMPT,
          messages: [{ role: "user", content: prompt }],
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).error?.message ?? `API error ${res.status}`);
      }

      setStatus("streaming");
      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]" || !raw) continue;
          try {
            const evt = JSON.parse(raw);
            if (evt.type === "content_block_delta" && evt.delta?.type === "text_delta") {
              setExpl((prev) => prev + evt.delta.text);
            }
          } catch { /* ignore malformed SSE chunks */ }
        }
      }

      setStatus("done");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Unknown error");
      setStatus("error");
    }
  }, [company, visible, technicals, rangeLabel]);

  if (visible.length < 2) return null;

  const isIdle     = status === "idle";
  const isDone     = status === "done";
  const isError    = status === "error";
  const isBusy     = status === "loading" || status === "streaming";
  const showButton = isIdle || isDone || isError;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs">✦</span>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">AI Price Analysis</p>
          </div>
          <p className="mt-0.5 text-[11px] text-hint">
            Educational breakdown · {rangeLabel} · {company.name}
          </p>
        </div>

        {showButton && (
          <button
            type="button"
            onClick={run}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90"
          >
            <span>✦</span>
            {isDone ? "Regenerate" : "Explain This Period"}
          </button>
        )}

        {status === "loading" && (
          <div className="flex items-center gap-2 text-xs text-muted">
            <div className="h-3 w-3 animate-spin rounded-full border border-rim border-t-accent" />
            Analysing {company.name} · {rangeLabel}…
          </div>
        )}

        {status === "streaming" && (
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
            Writing…
          </div>
        )}
      </div>

      {/* Error */}
      {isError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <p className="text-xs text-red-500">{errorMsg}</p>
        </div>
      )}

      {/* Idle hint */}
      {isIdle && (
        <div className="rounded-lg border border-seam bg-raised/60 px-4 py-3">
          <p className="text-xs text-muted">
            Click <strong className="text-sub">Explain This Period</strong> to get an AI-powered educational
            breakdown of what drove {company.ticker}'s price over the selected {rangeLabel} window.
            Uses price action and technical data — not financial advice.
          </p>
        </div>
      )}

      {/* Streaming / done */}
      {(isBusy || isDone) && explanation && (
        <div className="mt-1 rounded-lg border border-seam bg-raised/40 px-4 py-3">
          <Markdown text={explanation} />
          {status === "streaming" && (
            <span className="mt-1 inline-block h-3.5 w-0.5 animate-pulse bg-accent align-middle" />
          )}
        </div>
      )}
    </div>
  );
};
