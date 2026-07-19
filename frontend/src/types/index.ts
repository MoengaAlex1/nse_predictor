export interface PricePoint {
  date: string;
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
  current_price: number | null;
  change_pct_today: number | null;
  signal: "BUY" | "HOLD" | "SELL" | null;
  price_history: PricePoint[];
  price_preview: number[];
  last_updated: string | null;
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

export interface MarketOverviewDoc {
  date: string;
  top_gainers: { ticker: string; change_pct: number }[];
  top_losers: { ticker: string; change_pct: number }[];
  signal_distribution: { BUY: number; HOLD: number; SELL: number };
  sector_performance: Record<string, number>;
  nse20_value: number | null;
  nse20_change_pct: number | null;
}
