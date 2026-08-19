/** Typed API client. Single request<T>() + a flat api object (tickflow pattern). */

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

// ---- types -----------------------------------------------------------------
export interface StrategyMeta {
  id: string;
  name: string;
  description: string;
  tags: string[];
  params: { id: string; label: string; type: string; default: unknown; min?: number; max?: number; step?: number }[];
  order_by: string | null;
  descending: boolean;
  limit: number;
  entry_signals: string[];
  stop_loss: number | null;
  take_profit: number | null;
  max_hold_days: number | null;
  source: string;
}

export interface ScreenerHit {
  symbol: string;
  close: number;
  ret_1d: number | null;
  vol_ratio_20: number | null;
  rsi14: number | null;
  mom_20d: number | null;
  dist_52w_high: number | null;
  rvol_20d: number | null;
  [key: string]: unknown;
}

export interface ScreenerResult {
  strategy?: string;
  signal?: string;
  date: string | null;
  hits: ScreenerHit[];
  count: number;
  error?: string;
}

export interface SignalCondition {
  left: string;
  op: string;
  right: string;
  leftDays: number;
  rightDays: number;
}

export interface CustomSignal {
  id: string;
  name: string;
  enabled: boolean;
  conditions: SignalCondition[];
}

export interface SignalOptions {
  fields: string[];
  groups: Record<string, string[]>;
  operators: string[];
  maxDays: number;
  maxConditions: number;
}

export interface BacktestMetrics {
  n_trades: number;
  total_return?: number;
  ann_return?: number | null;
  ann_vol?: number;
  sharpe?: number | null;
  max_drawdown?: number;
  max_drawdown_days?: number;
  final_equity?: number;
  win_rate?: number;
  avg_win?: number | null;
  avg_loss?: number | null;
  profit_factor?: number | null;
  avg_hold_days?: number;
  exit_reasons?: Record<string, number>;
}

export interface Trade {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  shares: number;
  pnl: number;
  ret: number;
  hold_days: number;
  exit_reason: string;
}

export interface BacktestDone {
  strategy: string;
  config: Record<string, unknown>;
  metrics: BacktestMetrics;
  equity: { date: string; equity: number; positions: number }[];
  trades: Trade[];
  n_trades_total: number;
  cancelled: boolean;
}

export interface MonitorRule {
  id: string;
  name: string;
  enabled: boolean;
  type: "strategy" | "signal" | "price";
  scope: "all" | "symbols";
  symbols: string[];
  strategy_id?: string;
  logic: "and" | "or";
  conditions: SignalCondition[];
  severity: "info" | "warn" | "critical";
  cooldown_seconds: number;
  track_outcome: boolean;
}

export interface Alert {
  rule_id: string;
  rule_name: string;
  type: string;
  severity: "info" | "warn" | "critical";
  symbol: string;
  close: number;
  ret_1d: number | null;
  date: string;
  message: string;
  ts?: number;
}

export interface Outcome {
  id: string;
  symbol: string;
  entry_date: string;
  entry_price: number;
  strategy_id: string | null;
  target_pct: number;
  stop_pct: number;
  expiry_days: number;
  result?: "target_hit" | "stop_hit" | "expired";
  exit_price?: number;
  exit_date?: string;
  days_held?: number;
  ret?: number;
}

export interface Scorecard {
  strategy_id: string;
  period: string;
  n: number;
  win_rate: number;
  avg_ret: number;
  profit_factor: number | null;
  results: Record<string, number>;
}

export interface Dashboard {
  date: string | null;
  breadth: {
    advancers: number;
    decliners: number;
    above_ma200: number;
    total: number;
    new_highs_252d: number;
    new_lows_60d: number;
  };
  gainers: ScreenerHit[];
  losers: ScreenerHit[];
  sectors: { sector: string; avg_ret: number; n: number }[];
  spy: { date: string; close: number }[];
  strategy_counts: Record<string, number>;
  alerts: Alert[];
  scorecards: Scorecard[];
}

export interface DataStatus {
  latest_enriched: string | null;
  symbols: number | null;
  universe_size: number;
  pipeline: { state: string; stage: string | null; pct: number; message: string; last_run: string | null; errors: string[] };
}

// ---- endpoints ----------------------------------------------------------------
export const api = {
  health: () => request<{ ok: boolean; time: string }>("/health"),
  dashboard: () => request<Dashboard>("/dashboard"),
  dataStatus: () => request<DataStatus>("/data/status"),
  runPipeline: (lookbackDays = 30) =>
    request<{ started: boolean }>(`/data/pipeline/run?lookback_days=${lookbackDays}`, { method: "POST" }),
  candles: (symbol: string, days = 250) =>
    request<{ symbol: string; bars: { date: string; open: number; high: number; low: number; close: number; volume: number }[] }>(
      `/data/candles/${symbol}?days=${days}`),

  strategies: () => request<{ strategies: StrategyMeta[]; load_errors: { file: string; error: string }[] }>("/strategies"),
  screenerAll: () => request<{ date: string | null; counts: Record<string, number> }>("/screener/all"),
  screenerRun: (strategy: string, params?: Record<string, unknown>) =>
    request<ScreenerResult>(
      `/screener/run?strategy=${strategy}${params ? `&params=${encodeURIComponent(JSON.stringify(params))}` : ""}`),
  screenerCustom: (signalId: string) => request<ScreenerResult>(`/screener/custom/${signalId}`),

  customSignals: () => request<{ signals: CustomSignal[] }>("/custom-signals"),
  signalOptions: () => request<SignalOptions>("/custom-signals/options"),
  saveCustomSignal: (signal: CustomSignal) =>
    request<{ ok: boolean }>("/custom-signals", { method: "POST", body: JSON.stringify(signal) }),
  deleteCustomSignal: (id: string) => request<{ deleted: boolean }>(`/custom-signals/${id}`, { method: "DELETE" }),

  cancelBacktest: (req: Record<string, unknown>) =>
    request<{ cancelled: boolean }>("/backtest/cancel", { method: "POST", body: JSON.stringify({ request: req }) }),

  monitorRules: () => request<{ rules: MonitorRule[] }>("/monitor/rules"),
  saveRule: (rule: Partial<MonitorRule>) =>
    request<{ rule: MonitorRule }>("/monitor/rules", { method: "POST", body: JSON.stringify(rule) }),
  deleteRule: (id: string) => request<{ deleted: boolean }>(`/monitor/rules/${id}`, { method: "DELETE" }),
  runMonitor: () => request<{ alerts: Alert[]; count: number }>("/monitor/run", { method: "POST" }),
  alerts: (limit = 200) => request<{ alerts: Alert[] }>(`/monitor/alerts?limit=${limit}`),
  clearAlerts: () => request<{ cleared: number }>("/monitor/alerts", { method: "DELETE" }),
  outcomes: () => request<{ open: Outcome[]; closed: Outcome[]; scorecards: Scorecard[] }>("/monitor/outcomes"),

  generateStrategy: (description: string) =>
    request<{ code: string; meta: Record<string, unknown> | null; valid: boolean; error: string | null }>(
      "/strategies/generate", { method: "POST", body: JSON.stringify({ description }) }),
  saveStrategyCode: (code: string) =>
    request<{ valid: boolean; error: string | null; strategy?: StrategyMeta }>(
      "/strategies/save-code", { method: "POST", body: JSON.stringify({ code }) }),
};

export const QK = {
  dashboard: ["dashboard"] as const,
  dataStatus: ["dataStatus"] as const,
  strategies: ["strategies"] as const,
  screenerAll: ["screenerAll"] as const,
  screenerRun: (id: string, params?: Record<string, unknown>) => ["screenerRun", id, params] as const,
  screenerCustom: (id: string) => ["screenerCustom", id] as const,
  customSignals: ["customSignals"] as const,
  signalOptions: ["signalOptions"] as const,
  monitorRules: ["monitorRules"] as const,
  alerts: ["alerts"] as const,
  outcomes: ["outcomes"] as const,
  candles: (symbol: string) => ["candles", symbol] as const,
};
