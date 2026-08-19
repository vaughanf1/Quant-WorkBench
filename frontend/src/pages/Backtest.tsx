import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, RotateCcw, Square } from "lucide-react";
import { api, QK, type BacktestDone, type Trade } from "@/lib/api";
import {
  clearBacktest, startBacktest, stopBacktest, tryReconnect, useBacktestTask,
  type BacktestParams,
} from "@/lib/backtestTask";
import { dirClass, fmtMoney, fmtNum, fmtPct } from "@/lib/format";
import { cn } from "@/lib/cn";

const today = new Date().toISOString().slice(0, 10);
const DEFAULTS: BacktestParams = {
  strategy: "", start: "2024-01-01", end: today,
  commission_bps: 1, slippage_bps: 5,
  stop_loss: null, take_profit: null, max_hold_days: null, max_positions: 10,
};

export default function Backtest() {
  const task = useBacktestTask();
  const { data: strategies } = useQuery({ queryKey: QK.strategies, queryFn: api.strategies });
  const [form, setForm] = useState<BacktestParams>(DEFAULTS);

  useEffect(() => {
    tryReconnect(); // survive page refresh: reattach to a running job
  }, []);

  const selectedMeta = strategies?.strategies.find((s) => s.id === form.strategy);
  useEffect(() => {
    if (!form.strategy && strategies?.strategies.length) {
      setForm((f) => ({ ...f, strategy: strategies.strategies[0].id }));
    }
  }, [strategies, form.strategy]);

  const running = !!task && !task.result && !task.error;
  const set = (p: Partial<BacktestParams>) => setForm((f) => ({ ...f, ...p }));

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-3 lg:flex-row lg:items-start">
      {/* config */}
      <section className="panel w-full shrink-0 lg:w-72">
        <div className="panel-header">Backtest config</div>
        <div className="flex flex-col gap-2.5 p-2.5">
          <Field label="Strategy">
            <select className="input" value={form.strategy} onChange={(e) => set({ strategy: e.target.value })}>
              {strategies?.strategies.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Start">
              <input type="date" className="input" value={form.start} onChange={(e) => set({ start: e.target.value })} />
            </Field>
            <Field label="End">
              <input type="date" className="input" value={form.end} onChange={(e) => set({ end: e.target.value })} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Commission (bps)">
              <input type="number" className="input" value={form.commission_bps}
                onChange={(e) => set({ commission_bps: Number(e.target.value) })} />
            </Field>
            <Field label="Slippage (bps)">
              <input type="number" className="input" value={form.slippage_bps}
                onChange={(e) => set({ slippage_bps: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label={`Stop loss (default ${selectedMeta?.stop_loss != null ? fmtPct(selectedMeta.stop_loss, 0) : "—"})`}>
              <input type="number" step="0.01" className="input" placeholder="strategy default"
                value={form.stop_loss ?? ""}
                onChange={(e) => set({ stop_loss: e.target.value === "" ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Take profit">
              <input type="number" step="0.01" className="input" placeholder="off"
                value={form.take_profit ?? ""}
                onChange={(e) => set({ take_profit: e.target.value === "" ? null : Number(e.target.value) })} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label={`Max hold (default ${selectedMeta?.max_hold_days ?? "—"}d)`}>
              <input type="number" className="input" placeholder="strategy default"
                value={form.max_hold_days ?? ""}
                onChange={(e) => set({ max_hold_days: e.target.value === "" ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Max positions">
              <input type="number" className="input" value={form.max_positions}
                onChange={(e) => set({ max_positions: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="mt-1 flex gap-2">
            {running ? (
              <button className="btn flex-1 justify-center border-term-red text-term-red" onClick={() => stopBacktest()}>
                <Square size={11} /> Cancel
              </button>
            ) : (
              <button className="btn-accent flex-1 justify-center" disabled={!form.strategy}
                onClick={() => startBacktest(form)}>
                <Play size={11} /> Run backtest
              </button>
            )}
            {task && !running && (
              <button className="btn" onClick={() => clearBacktest()} aria-label="Clear result">
                <RotateCcw size={11} />
              </button>
            )}
          </div>
          <p className="font-sans text-[10px] leading-relaxed text-term-muted">
            Entries fill at the next day&apos;s open. A page refresh reattaches to a running job.
          </p>
        </div>
      </section>

      {/* results */}
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {!task && (
          <div className="panel p-8 text-center font-sans text-[11px] text-term-muted">
            Configure a run on the left. Progress streams live; long runs survive a refresh.
          </div>
        )}
        {task && (
          <>
            <ProgressPanel />
            {task.error && <div className="panel p-3 text-[11px] text-term-red">{task.error}</div>}
            {task.result && <ResultPanels result={task.result} />}
          </>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="sub-header">{label}</span>
      {children}
    </label>
  );
}

/* ---- progress ---------------------------------------------------------------- */
function ProgressPanel() {
  const task = useBacktestTask();
  if (!task || task.result) return null;
  const p = task.progress;
  const pct = p ? Math.round((p.day / p.total) * 100) : 0;
  return (
    <section className="panel">
      <div className="panel-header">
        <span>{task.params.strategy} · {task.params.start} → {task.params.end}</span>
        <span className="normal-case tracking-normal text-term-muted">
          {task.reconnecting ? "reconnecting…" : p ? `${p.date} · ${fmtMoney(p.equity)}` : "starting…"}
        </span>
      </div>
      <div className="p-3">
        <div className="h-2 w-full overflow-hidden rounded-sm bg-term-bg2">
          <div className={cn("h-full bg-term-accent transition-all", task.reconnecting && "animate-pulse")}
            style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-1 text-right text-[10px] num text-term-muted">{pct}%</div>
      </div>
    </section>
  );
}

/* ---- results ------------------------------------------------------------------ */
function ResultPanels({ result }: { result: BacktestDone }) {
  const m = result.metrics;
  return (
    <>
      <section className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
        <Metric label="Total return" value={fmtPct(m.total_return)} cls={dirClass(m.total_return)} />
        <Metric label="Annualised" value={fmtPct(m.ann_return)} cls={dirClass(m.ann_return)} />
        <Metric label="Sharpe" value={m.sharpe != null ? fmtNum(m.sharpe, 2) : "—"}
          cls={m.sharpe != null && m.sharpe > 1 ? "up" : "text-term-heading num"} />
        <Metric label="Max drawdown" value={fmtPct(m.max_drawdown)} cls="down" />
        <Metric label="Win rate" value={m.win_rate != null ? fmtPct(m.win_rate, 0) : "—"}
          cls={m.win_rate != null && m.win_rate >= 0.5 ? "up" : "text-term-heading num"} />
        <Metric label="Profit factor" value={m.profit_factor != null ? fmtNum(m.profit_factor, 2) : "—"}
          cls={m.profit_factor != null && m.profit_factor > 1 ? "up" : "down"} />
        <Metric label="Trades" value={String(m.n_trades)} cls="text-term-heading num" />
        <Metric label="Avg hold" value={m.avg_hold_days != null ? `${fmtNum(m.avg_hold_days, 1)}d` : "—"}
          cls="text-term-heading num" />
      </section>

      <EquityPanel result={result} />
      <TradesPanel trades={result.trades} total={result.n_trades_total}
        exitReasons={m.exit_reasons} />
    </>
  );
}

function Metric({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="panel px-2.5 py-2">
      <div className="sub-header">{label}</div>
      <div className={cn("mt-0.5 text-[15px]", cls)}>{value}</div>
    </div>
  );
}

/* equity curve with drawdown shading, hand-rolled SVG */
function EquityPanel({ result }: { result: BacktestDone }) {
  const eq = result.equity;
  const path = useMemo(() => {
    if (eq.length < 2) return null;
    const W = 1000, H = 260, PAD = 8;
    const vals = eq.map((p) => p.equity);
    const min = Math.min(...vals), max = Math.max(...vals);
    const span = max - min || 1;
    const x = (i: number) => PAD + (i / (eq.length - 1)) * (W - PAD * 2);
    const y = (v: number) => H - PAD - ((v - min) / span) * (H - PAD * 2);
    const line = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    // drawdown shading: area between running peak and equity
    let peak = vals[0];
    const peaks = vals.map((v) => (peak = Math.max(peak, v)));
    const ddTop = peaks.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const ddBottom = [...vals].reverse()
      .map((v, i) => `L${x(eq.length - 1 - i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const baseline = y(vals[0]);
    return { W, H, line, dd: `${ddTop} ${ddBottom} Z`, baseline };
  }, [eq]);

  if (!path) return null;
  const first = eq[0], last = eq[eq.length - 1];
  const gain = last.equity >= first.equity;
  return (
    <section className="panel">
      <div className="panel-header">
        <span>Equity curve</span>
        <span className="normal-case tracking-normal num text-term-muted">
          {first.date} → {last.date} · final {fmtMoney(last.equity)}
        </span>
      </div>
      <div className="p-2">
        <svg viewBox={`0 0 ${path.W} ${path.H}`} className="h-64 w-full">
          <path d={path.dd} fill="rgba(255,59,59,0.10)" />
          <line x1="0" x2={path.W} y1={path.baseline} y2={path.baseline}
            stroke="#2a2a2a" strokeDasharray="4 4" />
          <path d={path.line} fill="none" stroke={gain ? "#22ee22" : "#ff3b3b"} strokeWidth="1.75" />
        </svg>
      </div>
    </section>
  );
}

const REASON_TAG: Record<string, string> = {
  stop_loss: "border-term-red text-term-red",
  take_profit: "border-term-green text-term-green",
  max_hold: "border-term-border text-term-muted",
  end_of_data: "border-term-border text-term-muted",
};

function TradesPanel({ trades, total, exitReasons }: {
  trades: Trade[]; total: number; exitReasons?: Record<string, number>;
}) {
  const [sortKey, setSortKey] = useState<keyof Trade>("entry_date");
  const [desc, setDesc] = useState(true);
  const sorted = useMemo(() => {
    const rows = [...trades];
    rows.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      const c = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return desc ? -c : c;
    });
    return rows;
  }, [trades, sortKey, desc]);

  const header = (key: keyof Trade, label: string, right = true) => (
    <th className={cn(right && "text-right", "cursor-pointer select-none hover:text-term-accent")}
      onClick={() => (sortKey === key ? setDesc(!desc) : (setSortKey(key), setDesc(true)))}>
      {label}{sortKey === key ? (desc ? " ↓" : " ↑") : ""}
    </th>
  );

  return (
    <section className="panel">
      <div className="panel-header">
        <span>Trades · showing {trades.length}{total > trades.length ? ` of ${total}` : ""}</span>
        {exitReasons && (
          <span className="flex gap-2 normal-case tracking-normal text-term-muted">
            {Object.entries(exitReasons).map(([k, v]) => (
              <span key={k}>{k.replaceAll("_", " ")} <span className="num text-term-text">{v}</span></span>
            ))}
          </span>
        )}
      </div>
      <div className="scroll-thin max-h-[420px] overflow-auto">
        <table className="grid-data">
          <thead>
            <tr>
              {header("symbol", "Sym", false)}
              {header("entry_date", "Entry", false)}
              {header("exit_date", "Exit", false)}
              {header("entry_price", "In")}
              {header("exit_price", "Out")}
              {header("ret", "Return")}
              {header("pnl", "P&L")}
              {header("hold_days", "Days")}
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t, i) => (
              <tr key={`${t.symbol}-${t.entry_date}-${i}`}>
                <td className="font-semibold text-term-heading">{t.symbol}</td>
                <td className="text-term-muted">{t.entry_date}</td>
                <td className="text-term-muted">{t.exit_date}</td>
                <td className="text-right">{fmtNum(t.entry_price)}</td>
                <td className="text-right">{fmtNum(t.exit_price)}</td>
                <td className={cn("text-right", dirClass(t.ret))}>{fmtPct(t.ret)}</td>
                <td className={cn("text-right", dirClass(t.pnl))}>{fmtMoney(t.pnl)}</td>
                <td className="text-right text-term-muted">{t.hold_days}</td>
                <td><span className={cn("tag", REASON_TAG[t.exit_reason])}>{t.exit_reason.replaceAll("_", " ")}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
