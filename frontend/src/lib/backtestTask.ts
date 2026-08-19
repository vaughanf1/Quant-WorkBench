/** Module-level backtest task store (tickflow pattern).
 *
 * Lives outside React via useSyncExternalStore so it survives navigation;
 * the request query string is persisted to localStorage so a page refresh
 * reconnects to the same stream — the backend keys jobs by a hash of the
 * params, so reconnecting attaches to the running job instead of restarting.
 */
import { useSyncExternalStore } from "react";
import type { BacktestDone } from "@/lib/api";

export interface BacktestParams {
  strategy: string;
  start: string;
  end: string;
  commission_bps: number;
  slippage_bps: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  max_hold_days?: number | null;
  max_positions: number;
}

export interface BacktestTask {
  params: BacktestParams;
  progress: { day: number; total: number; date: string; equity: number } | null;
  result: BacktestDone | null;
  error: string | null;
  reconnecting: boolean;
}

const RECONNECT_KEY = "backtest_reconnect";
const MAX_RECONNECT_ATTEMPTS = 5;

let current: BacktestTask | null = null;
let es: EventSource | null = null;
let reconnectAttempts = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function set(patch: Partial<BacktestTask>) {
  if (!current) return;
  current = { ...current, ...patch };
  emit();
}

function buildQuery(p: BacktestParams): string {
  const q = new URLSearchParams();
  q.set("strategy", p.strategy);
  q.set("start", p.start);
  q.set("end", p.end);
  q.set("commission_bps", String(p.commission_bps));
  q.set("slippage_bps", String(p.slippage_bps));
  q.set("max_positions", String(p.max_positions));
  if (p.stop_loss != null) q.set("stop_loss", String(p.stop_loss));
  if (p.take_profit != null) q.set("take_profit", String(p.take_profit));
  if (p.max_hold_days != null) q.set("max_hold_days", String(p.max_hold_days));
  return q.toString();
}

function connect(qs: string) {
  es?.close();
  es = new EventSource(`/api/backtest/stream?${qs}`);

  es.addEventListener("open", () => {
    reconnectAttempts = 0;
    set({ reconnecting: false });
  });
  es.addEventListener("progress", (e) => {
    reconnectAttempts = 0;
    set({ progress: JSON.parse((e as MessageEvent).data), reconnecting: false });
  });
  es.addEventListener("done", (e) => {
    const result = JSON.parse((e as MessageEvent).data) as BacktestDone;
    localStorage.removeItem(RECONNECT_KEY);
    es?.close();
    es = null;
    set({ result, reconnecting: false });
  });
  es.addEventListener("error", (e) => {
    const msg = (e as MessageEvent).data;
    if (msg) {
      // server-pushed terminal error
      localStorage.removeItem(RECONNECT_KEY);
      es?.close();
      es = null;
      set({ error: String(msg), reconnecting: false });
      return;
    }
    // transport drop: EventSource retries automatically, bounded by our counter
    reconnectAttempts += 1;
    if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
      es?.close();
      es = null;
      set({ error: "Connection lost — run again to reattach.", reconnecting: false });
    } else {
      set({ reconnecting: true });
    }
  });
}

export function startBacktest(params: BacktestParams) {
  const qs = buildQuery(params);
  localStorage.setItem(RECONNECT_KEY, JSON.stringify({ qs, params }));
  current = { params, progress: null, result: null, error: null, reconnecting: false };
  reconnectAttempts = 0;
  emit();
  connect(qs);
}

export function tryReconnect() {
  if (current || es) return;
  const stored = localStorage.getItem(RECONNECT_KEY);
  if (!stored) return;
  try {
    const { qs, params } = JSON.parse(stored);
    current = { params, progress: null, result: null, error: null, reconnecting: true };
    emit();
    connect(qs);
  } catch {
    localStorage.removeItem(RECONNECT_KEY);
  }
}

export async function stopBacktest() {
  if (!current) return;
  const p = current.params;
  const req: Record<string, unknown> = {
    strategy: p.strategy, start: p.start, end: p.end,
    commission_bps: p.commission_bps, slippage_bps: p.slippage_bps,
    max_positions: p.max_positions,
  };
  if (p.stop_loss != null) req.stop_loss = p.stop_loss;
  if (p.take_profit != null) req.take_profit = p.take_profit;
  if (p.max_hold_days != null) req.max_hold_days = p.max_hold_days;
  const { api } = await import("@/lib/api");
  await api.cancelBacktest(req).catch(() => undefined);
}

export function clearBacktest() {
  es?.close();
  es = null;
  localStorage.removeItem(RECONNECT_KEY);
  current = null;
  emit();
}

export function useBacktestTask(): BacktestTask | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => current,
    () => null,
  );
}
