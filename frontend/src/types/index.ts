export interface PricePoint {
  date: string;
  price: number;
}

export interface IntradayPoint {
  time: string;
  price: number;
}

export interface CompanyDoc {
  id: string;
  ticker: string;
  name: string;
  short: string;
  sector: string;
  color: string;
  icon: string;
  csv: string;
  description?: string;
  current_price: number | null;
  change_pct_today: number | null;
  signal: "BUY" | "HOLD" | "SELL" | null;
  price_history: PricePoint[];
  price_preview: number[];
  price_date: string | null;
  last_updated: string | null;
  intraday_today?: IntradayPoint[];
  intraday_date?: string;
}

export interface SnapshotDoc {
  run_date: string;
  next_trading_day: string;
  forecast_dates?: string[];
  signal: "BUY" | "HOLD" | "SELL";
  risk_adjusted_signal: "BUY" | "HOLD" | "SELL";
  current_price_KES: number;
  predicted_price_KES: number;
  predicted_change_pct: number;
  var_95_pct: number;
  rationale: string;
  metrics: {
    rmse: number;
    mae: number;
    mape: number;
    directional_accuracy: number;
  };
  actuals: number[];
  preds: number[];
  forecast: number[];
  recent_mape?: number;
  recent_direction_acc?: number;
  signal_reasons?: string[];
  signal_implications?: string;
  confidence_score?: number;
  model_agreement?: number;
  model_breakdown?: Record<string, { price: number; signal: string; pct: number }>;
}

export interface TechnicalsDoc {
  date: string;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_upper: number | null;
  bb_mid: number | null;
  bb_lower: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_12: number | null;
  ema_26: number | null;
  volume: number;
  avg_volume_30d: number;
  daily_return: number | null;
  volatility_30d: number | null;
  monthly_heatmap: Record<string, number>;
}

export interface CorporateEvent {
  date: string;
  type: "earnings" | "dividend" | "rights_issue" | "expansion" | "management" | "regulatory" | "restructuring" | "other";
  title: string;
  summary: string;
}

export interface EventsDoc {
  items: CorporateEvent[];
}

export interface FinancialResult {
  period: string;
  period_end: string;
  period_type: "annual" | "interim";
  announcement_date: string;
  revenue_kes_mn: number | null;
  net_income_kes_mn: number | null;
  eps: number | null;
  bvps: number | null;
  notes?: string;
}

export interface DividendEvent {
  announcement_date: string;
  ex_date: string | null;
  payment_date: string | null;
  amount_kes: number | null;
  type: "final" | "interim" | "total" | "special" | "scrip" | "bonus" | "none";
  // Set by refresh_nse_disclosures.py when the title references a fiscal
  // period (FY2024, H1 2025, etc.). Used as an ex-date fallback for
  // display when a PDF-derived ex_date isn't yet available.
  period?: string | null;
  period_end?: string | null;
  title?: string;
  url?: string;
  source?: string;
  notes?: string;
}

export interface CorporateAction {
  date: string;
  type: string;
  details?: string;  // legacy format
  title?: string;    // new format (scraped from NSE)
  url?: string;      // new format (PDF link)
}

export interface NSEAnnouncement {
  date: string;
  type: "financial_result" | "corporate_action" | "dividend" | "agm";
  title: string;
  url: string;
}

export interface FinancialsDoc {
  annual: FinancialResult[];
  dividends: DividendEvent[];
  corporate_actions: CorporateAction[];
  announcements?: NSEAnnouncement[];
}

export interface CBKRateDecision {
  date: string;
  rate: number;
  change_bps: number;
  decision: "hike" | "cut" | "hold";
  notes?: string;
}

export interface MacroEvent {
  date: string;
  type: string;
  title: string;
  description: string;
}

export interface MacroDoc {
  cbk_rates: CBKRateDecision[];
  annual_inflation: Record<string, number>;
  kes_usd_year_end: Record<string, number>;
  nse20_year_end: Record<string, number>;
  macro_events: MacroEvent[];
}

export interface MarketOverviewDoc {
  date: string;
  top_gainers: { ticker: string; change_pct: number }[];
  top_losers: { ticker: string; change_pct: number }[];
  signal_distribution: { BUY: number; HOLD: number; SELL: number };
  sector_performance: Record<string, number>;
  nse20_value: number | null;
  nse20_change_pct: number | null;
}

export interface FundamentalsEstimate {
  period: string;
  eps_kes: number | null;
  revenue_kes_mn: number | null;
  net_income_kes_mn: number | null;
  pe_forward: number | null;
  source: "consensus" | "management";
}

export interface FundamentalsDoc {
  ticker: string;
  updated_at: string;
  shares_outstanding_mn: number | null;
  enterprise_value_kes_bn: number | null;
  employees: number | null;
  estimates: FundamentalsEstimate[];
}

export interface NewsItem {
  id: string;
  date: string;
  title: string;
  category: "earnings" | "dividend" | "regulatory" | "agm" | "corporate_action" | "general";
  body: string | null;
  url: string | null;
  source: "NSE" | "scraper";
}
