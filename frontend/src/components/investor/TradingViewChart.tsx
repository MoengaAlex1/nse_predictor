import { useEffect, useRef, useState } from "react";
import type { FC } from "react";

// TradingView's Advanced Chart widget. Embedded via the official
// s3.tradingview.com/tv.js loader — this is TradingView's own
// documented redistribution path (see tradingview.com/widget/advanced-chart)
// so we're using their licensed embed, NOT scraping. Users get their full
// chart UX (drawing tools, 100+ indicators, timeframe toggles) for visual
// analysis alongside our own model-driven views.
//
// Not all NSE tickers may exist on TradingView — the widget renders its
// own "Invalid symbol" state when that's the case, so we don't need to
// pre-validate. Wrapped in a hide/show toggle so a broken symbol doesn't
// take up screen space on a deep-dive.

// Ambient declaration so TS accepts the injected global. TradingView
// exposes `TradingView.widget` on window once tv.js loads.
declare global {
  interface Window {
    TradingView?: {
      widget: new (opts: Record<string, unknown>) => unknown;
    };
  }
}

const SCRIPT_ID = "tradingview-tv-js";
const SCRIPT_SRC = "https://s3.tradingview.com/tv.js";

function loadTradingViewScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.TradingView) return Promise.resolve();
  const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("tv.js failed")));
    });
  }
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.id = SCRIPT_ID;
    s.src = SCRIPT_SRC;
    s.async = true;
    s.addEventListener("load", () => resolve());
    s.addEventListener("error", () => reject(new Error("tv.js failed")));
    document.head.appendChild(s);
  });
}

interface Props {
  /** NSE short-form ticker (SCOM, KCB, EQTY...). Rendered as NSEKE:SCOM. */
  short: string;
  /** Company display name for the collapsed-panel label. */
  name?: string;
  /** Dark/light theme. Defaults to dark to match the app shell. */
  theme?: "light" | "dark";
  /** Container height in pixels. Widget is responsive on width. */
  height?: number;
  /** Default timeframe: 'D' = daily, '60' = 60min, '15' = 15min. */
  interval?: "1" | "5" | "15" | "30" | "60" | "D" | "W";
  /** Start collapsed. Default is now `false` (2026-09-21) — users
   *  asked for the TradingView chart to render as the primary
   *  chart on the deep-dive, not hidden behind a click. Pass `true`
   *  explicitly when placing the widget somewhere non-primary and
   *  the ~500KB load matters. */
  startCollapsed?: boolean;
}

export const TradingViewChart: FC<Props> = ({
  short, name, theme = "dark", height = 620, interval = "D",
  startCollapsed = false,
}) => {
  const [open, setOpen] = useState(!startCollapsed);
  const [error, setError] = useState<string | null>(null);
  const containerId = `tv-widget-${short}`;
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    loadTradingViewScript()
      .then(() => {
        if (cancelled) return;
        if (!window.TradingView || !mountRef.current) {
          setError("TradingView failed to initialise");
          return;
        }
        // Clear any previous instance before mounting a new one.
        mountRef.current.innerHTML = "";
        const inner = document.createElement("div");
        inner.id = containerId;
        inner.style.width = "100%";
        inner.style.height = `${height}px`;
        mountRef.current.appendChild(inner);
        try {
          new window.TradingView.widget({
            autosize: true,
            symbol: `NSEKE:${short.toUpperCase()}`,
            interval,
            timezone: "Africa/Nairobi",
            theme,
            style: "1",
            locale: "en",
            toolbar_bg: theme === "dark" ? "#0f1114" : "#f1f3f6",
            enable_publishing: false,
            // Every panel from the reference screenshot enabled:
            hide_side_toolbar: false,     // left drawing-tools rail
            hide_top_toolbar:  false,     // top symbol / timeframe / indicators bar
            hide_legend:       false,     // ticker + OHLC caption on chart
            hide_volume:       false,     // volume histogram under price
            allow_symbol_change: true,    // header symbol picker
            withdateranges:    true,      // bottom 1D 5D 1M 3M 6M YTD 1Y 5Y All
            details:           true,      // right-side symbol details panel
            hotlist:           true,      // right-side "top movers" tab
            calendar:          true,      // right-side economic calendar tab
            watchlist:         [          // pre-loaded watchlist mirroring the ref
              `NSEKE:${short.toUpperCase()}`,
              "NSEKE:SCOM", "NSEKE:EQTY", "NSEKE:KCB",
              "NSEKE:EABL", "NSEKE:COOP", "NSEKE:ABSA",
            ],
            news:              ["headlines"], // top-of-panel news headlines
            save_image:        true,      // screenshot button
            show_popup_button: true,      // pop-out button
            studies:           [
              "Volume@tv-basicstudies",   // pre-mounted volume study
            ],
            support_host: "https://www.tradingview.com",
            container_id: containerId,
          });
        } catch (e) {
          setError(String(e));
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
      // Clear the container so a repeated mount (e.g. HMR) starts clean.
      if (mountRef.current) mountRef.current.innerHTML = "";
    };
  }, [open, short, theme, height, interval, containerId]);

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between border-b border-seam px-5 py-3 text-left transition-colors hover:bg-raised/40"
        aria-expanded={open}
      >
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            TradingView Reference Chart
          </p>
          <p className="mt-0.5 text-xs text-sub">
            {name ? `${name} · ` : ""}NSEKE:{short}{" "}
            <span className="text-hint">
              · third-party display · not used by our model
            </span>
          </p>
        </div>
        <span className="font-mono text-xs text-hint">{open ? "▲ hide" : "▼ show"}</span>
      </button>

      {open && (
        <div className="p-2">
          {error && (
            <div className="rounded-md border border-red-800/60 bg-red-950/30 px-4 py-3 text-sm text-red-300">
              TradingView widget couldn't load: {error}. This ticker may not
              be listed on TradingView, or a network/ad-block extension is
              blocking their embed script.
            </div>
          )}
          <div
            ref={mountRef}
            className="tradingview-widget-container"
            style={{ minHeight: height }}
          />
          <p className="mt-2 px-2 text-[10px] text-hint">
            Chart powered by{" "}
            <a
              href={`https://www.tradingview.com/symbols/NSEKE-${short}/`}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-accent"
            >
              TradingView
            </a>
            . Data delayed per their free-tier terms.
          </p>
        </div>
      )}
    </div>
  );
};
