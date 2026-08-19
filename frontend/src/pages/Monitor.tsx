import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Plus, Trash2, X } from "lucide-react";
import {
  api, QK,
  type Alert, type MonitorRule, type Outcome, type Scorecard, type SignalCondition, type StrategyMeta,
} from "@/lib/api";
import { dirClass, fmtNum, fmtPct, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/cn";

export default function Monitor() {
  const [editorOpen, setEditorOpen] = useState(false);
  return (
    <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-3 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex min-w-0 flex-col gap-3">
        <AlertsFeed />
        <OutcomesPanel />
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <RulesPanel onAdd={() => setEditorOpen(true)} />
        <ScorecardsPanel />
      </div>
      {editorOpen && <RuleEditor onClose={() => setEditorOpen(false)} />}
    </div>
  );
}

/* ---- alerts feed --------------------------------------------------------- */
const SEV_TEXT: Record<string, string> = {
  info: "text-term-cyan", warn: "text-term-accent", critical: "text-term-red",
};

function AlertsFeed() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: QK.alerts, queryFn: () => api.alerts(200), refetchInterval: 30_000 });
  const run = useMutation({
    mutationFn: api.runMonitor,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.alerts });
      qc.invalidateQueries({ queryKey: QK.outcomes });
    },
  });
  const clear = useMutation({
    mutationFn: api.clearAlerts,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.alerts }),
  });

  return (
    <section className="panel">
      <div className="panel-header">
        <span>Alert feed</span>
        <div className="flex gap-2 normal-case tracking-normal">
          <button className="btn h-6 px-2 py-0" disabled={run.isPending} onClick={() => run.mutate()}>
            <BellRing size={11} /> {run.isPending ? "Running…" : "Run monitor pass"}
          </button>
          <button className="btn h-6 px-2 py-0" onClick={() => clear.mutate()}>Clear</button>
        </div>
      </div>
      {!data || data.alerts.length === 0 ? (
        <div className="p-4 font-sans text-[11px] text-term-muted">
          No alerts yet. Rules are evaluated on every post-market pipeline run, or run a pass now.
        </div>
      ) : (
        <div className="scroll-thin max-h-[420px] overflow-y-auto">
          {data.alerts.map((a: Alert, i: number) => (
            <div key={i} className="flex items-baseline gap-2 border-b border-term-borderSoft px-2.5 py-1.5 text-[11px]">
              <span className={cn("tag border-current shrink-0", SEV_TEXT[a.severity])}>{a.severity}</span>
              <span className="font-semibold text-term-heading">{a.symbol}</span>
              <span className="truncate text-term-text">{a.message}</span>
              <span className="ml-auto shrink-0 num text-term-muted">{fmtPrice(a.close)}</span>
              <span className="shrink-0 num text-term-muted">{a.date}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ---- rules ---------------------------------------------------------------- */
function RulesPanel({ onAdd }: { onAdd: () => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: QK.monitorRules, queryFn: api.monitorRules });
  const del = useMutation({
    mutationFn: api.deleteRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.monitorRules }),
  });
  const toggle = useMutation({
    mutationFn: (rule: MonitorRule) => api.saveRule({ ...rule, enabled: !rule.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.monitorRules }),
  });

  return (
    <section className="panel">
      <div className="panel-header">
        <span>Rules</span>
        <button className="btn h-6 px-2 py-0 normal-case tracking-normal" onClick={onAdd}>
          <Plus size={11} /> New rule
        </button>
      </div>
      {!data || data.rules.length === 0 ? (
        <div className="p-4 font-sans text-[11px] text-term-muted">
          No rules defined. A rule watches a strategy or a condition set and raises an alert when it fires.
        </div>
      ) : (
        <div className="flex flex-col">
          {data.rules.map((r) => (
            <div key={r.id} className="flex items-center gap-2 border-b border-term-borderSoft px-2.5 py-2 text-[11px]">
              <button
                onClick={() => toggle.mutate(r)}
                className={cn("h-3 w-6 shrink-0 rounded-full border transition-colors",
                  r.enabled ? "border-term-accent bg-term-accentSubtle" : "border-term-border bg-term-bg2")}
                aria-label={r.enabled ? `Disable ${r.name}` : `Enable ${r.name}`}
              >
                <span className={cn("block h-2 w-2 rounded-full transition-transform",
                  r.enabled ? "translate-x-3 bg-term-accent" : "translate-x-0.5 bg-term-muted")} />
              </button>
              <div className="min-w-0 flex-1">
                <div className={cn("truncate font-semibold", r.enabled ? "text-term-heading" : "text-term-muted")}>
                  {r.name}
                </div>
                <div className="truncate text-[10px] text-term-muted">
                  {r.type === "strategy"
                    ? `strategy · ${r.strategy_id}`
                    : r.conditions.map((c) => `${c.left} ${c.op} ${String(c.right).replace("field:", "")}`)
                        .join(r.logic === "or" ? " OR " : " AND ")}
                  {r.scope === "symbols" && ` · ${r.symbols.join(",")}`}
                </div>
              </div>
              <span className={cn("tag border-current shrink-0", SEV_TEXT[r.severity])}>{r.severity}</span>
              {r.track_outcome && <span className="tag shrink-0 border-term-cyan text-term-cyan">tracked</span>}
              <button onClick={() => del.mutate(r.id)} className="shrink-0 text-term-muted hover:text-term-red"
                aria-label={`Delete ${r.name}`}>
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ---- outcomes -------------------------------------------------------------- */
const RESULT_TAG: Record<string, string> = {
  target_hit: "border-term-green text-term-green",
  stop_hit: "border-term-red text-term-red",
  expired: "border-term-border text-term-muted",
};

function OutcomesPanel() {
  const { data } = useQuery({ queryKey: QK.outcomes, queryFn: api.outcomes, refetchInterval: 60_000 });
  return (
    <section className="panel">
      <div className="panel-header">
        <span>Signal outcomes</span>
        <span className="normal-case tracking-normal text-term-muted">
          {data ? `${data.open.length} open · ${data.closed.length} resolved` : "…"}
        </span>
      </div>
      {!data || (data.open.length === 0 && data.closed.length === 0) ? (
        <div className="p-4 font-sans text-[11px] text-term-muted">
          Nothing tracked yet. Enable &quot;track outcome&quot; on a rule and fired signals get resolved
          against target, stop, or expiry on each pipeline run.
        </div>
      ) : (
        <div className="scroll-thin max-h-[380px] overflow-auto">
          <table className="grid-data">
            <thead>
              <tr>
                <th>Sym</th><th>Strategy</th><th>Entry</th><th className="text-right">@</th>
                <th>Status</th><th className="text-right">Return</th><th className="text-right">Days</th>
              </tr>
            </thead>
            <tbody>
              {data.open.map((o: Outcome) => (
                <tr key={o.id}>
                  <td className="font-semibold text-term-heading">{o.symbol}</td>
                  <td className="text-term-muted">{o.strategy_id ?? "manual"}</td>
                  <td className="text-term-muted">{o.entry_date}</td>
                  <td className="text-right">{fmtNum(o.entry_price)}</td>
                  <td><span className="tag border-term-accent text-term-accent">open</span></td>
                  <td className="text-right text-term-muted">
                    →{fmtPct(o.target_pct, 0)} / {fmtPct(o.stop_pct, 0)}
                  </td>
                  <td className="text-right text-term-muted">≤{o.expiry_days}</td>
                </tr>
              ))}
              {data.closed.map((o: Outcome) => (
                <tr key={o.id}>
                  <td className="font-semibold text-term-heading">{o.symbol}</td>
                  <td className="text-term-muted">{o.strategy_id ?? "manual"}</td>
                  <td className="text-term-muted">{o.entry_date}</td>
                  <td className="text-right">{fmtNum(o.entry_price)}</td>
                  <td><span className={cn("tag", RESULT_TAG[o.result ?? ""])}>{o.result?.replaceAll("_", " ")}</span></td>
                  <td className={cn("text-right", dirClass(o.ret))}>{fmtPct(o.ret)}</td>
                  <td className="text-right text-term-muted">{o.days_held}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ScorecardsPanel() {
  const { data } = useQuery({ queryKey: QK.outcomes, queryFn: api.outcomes });
  const cards = data?.scorecards ?? [];
  return (
    <section className="panel">
      <div className="panel-header">Rolling scorecards</div>
      {cards.length === 0 ? (
        <div className="p-4 font-sans text-[11px] text-term-muted">
          Win rate and profit factor per strategy over 7 and 30 days, built from resolved outcomes.
        </div>
      ) : (
        <table className="grid-data">
          <thead>
            <tr>
              <th>Strategy</th><th>Window</th><th className="text-right">N</th>
              <th className="text-right">Win</th><th className="text-right">Avg ret</th><th className="text-right">PF</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((c: Scorecard, i: number) => (
              <tr key={i}>
                <td className="text-term-heading">{c.strategy_id}</td>
                <td className="text-term-muted">{c.period}</td>
                <td className="text-right">{c.n}</td>
                <td className={cn("text-right", c.win_rate >= 0.5 ? "up" : "down")}>{fmtPct(c.win_rate, 0)}</td>
                <td className={cn("text-right", dirClass(c.avg_ret))}>{fmtPct(c.avg_ret)}</td>
                <td className="text-right">{c.profit_factor != null ? fmtNum(c.profit_factor, 2) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/* ---- rule editor --------------------------------------------------------------- */
const EMPTY_COND: SignalCondition = { left: "close", op: ">", right: "field:ma20", leftDays: 0, rightDays: 0 };

function RuleEditor({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: strategies } = useQuery({ queryKey: QK.strategies, queryFn: api.strategies });
  const { data: options } = useQuery({ queryKey: QK.signalOptions, queryFn: api.signalOptions });

  const [rule, setRule] = useState<Partial<MonitorRule>>({
    name: "", type: "strategy", strategy_id: "", scope: "all", symbols: [],
    logic: "and", conditions: [{ ...EMPTY_COND }], severity: "info",
    cooldown_seconds: 3600, track_outcome: true, enabled: true,
  });
  const [symbolsText, setSymbolsText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const payload = { ...rule, symbols: symbolsText.split(/[\s,]+/).filter(Boolean).map((s) => s.toUpperCase()) };
      if (payload.scope === "symbols" && payload.symbols!.length === 0) throw new Error("Add at least one symbol");
      return api.saveRule(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.monitorRules });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const set = (p: Partial<MonitorRule>) => setRule((r) => ({ ...r, ...p }));
  const patchCond = (i: number, p: Partial<SignalCondition>) =>
    set({ conditions: rule.conditions!.map((c, j) => (j === i ? { ...c, ...p } : c)) });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="panel max-h-[85vh] w-full max-w-2xl overflow-y-auto scroll-thin shadow-panel"
        onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <span>New monitor rule</span>
          <button onClick={onClose} className="text-term-muted hover:text-term-text" aria-label="Close editor">
            <X size={13} />
          </button>
        </div>
        <div className="flex flex-col gap-3 p-3">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Rule name">
              <input className="input" value={rule.name} onChange={(e) => set({ name: e.target.value })}
                placeholder="Breakouts on watchlist" />
            </Field>
            <Field label="Type">
              <select className="input" value={rule.type}
                onChange={(e) => set({ type: e.target.value as MonitorRule["type"] })}>
                <option value="strategy">strategy hit</option>
                <option value="signal">signal conditions</option>
                <option value="price">price conditions</option>
              </select>
            </Field>
          </div>

          {rule.type === "strategy" ? (
            <Field label="Strategy">
              <select className="input" value={rule.strategy_id}
                onChange={(e) => set({ strategy_id: e.target.value })}>
                <option value="">— choose —</option>
                {strategies?.strategies.map((s: StrategyMeta) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </Field>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <span className="sub-header">Conditions</span>
                <label className="flex items-center gap-1 text-[10px] text-term-muted">
                  fold with
                  <select className="input w-16" value={rule.logic}
                    onChange={(e) => set({ logic: e.target.value as "and" | "or" })}>
                    <option value="and">AND</option>
                    <option value="or">OR</option>
                  </select>
                </label>
              </div>
              {rule.conditions!.map((c, i) => (
                <div key={i} className="flex flex-wrap items-center gap-1.5 border border-term-borderSoft bg-term-bg2 p-1.5">
                  <select className="input w-40" value={c.left} onChange={(e) => patchCond(i, { left: e.target.value })}>
                    {options && Object.entries(options.groups).map(([g, fs]) => (
                      <optgroup key={g} label={g}>{fs.map((f) => <option key={f} value={f}>{f}</option>)}</optgroup>
                    ))}
                  </select>
                  <select className="input w-14" value={c.op} onChange={(e) => patchCond(i, { op: e.target.value })}>
                    {(options?.operators ?? [">", "<"]).map((op) => <option key={op} value={op}>{op}</option>)}
                  </select>
                  <input className="input w-28" value={String(c.right)}
                    onChange={(e) => patchCond(i, { right: e.target.value })}
                    placeholder="number or field:ma20" />
                  {rule.conditions!.length > 1 && (
                    <button onClick={() => set({ conditions: rule.conditions!.filter((_, j) => j !== i) })}
                      className="text-term-muted hover:text-term-red" aria-label="Remove condition">
                      <X size={12} />
                    </button>
                  )}
                </div>
              ))}
              <button className="btn self-start"
                onClick={() => set({ conditions: [...rule.conditions!, { ...EMPTY_COND }] })}>
                <Plus size={11} /> Add condition
              </button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <Field label="Scope">
              <select className="input" value={rule.scope}
                onChange={(e) => set({ scope: e.target.value as "all" | "symbols" })}>
                <option value="all">whole universe</option>
                <option value="symbols">specific symbols</option>
              </select>
            </Field>
            {rule.scope === "symbols" && (
              <Field label="Symbols (comma / space separated)">
                <input className="input" value={symbolsText} onChange={(e) => setSymbolsText(e.target.value)}
                  placeholder="AAPL, NVDA, MSFT" />
              </Field>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Field label="Severity">
              <select className="input" value={rule.severity}
                onChange={(e) => set({ severity: e.target.value as MonitorRule["severity"] })}>
                <option value="info">info</option>
                <option value="warn">warn</option>
                <option value="critical">critical</option>
              </select>
            </Field>
            <Field label="Cooldown (seconds)">
              <input type="number" className="input" value={rule.cooldown_seconds}
                onChange={(e) => set({ cooldown_seconds: Number(e.target.value) })} />
            </Field>
            <label className="flex items-end gap-2 pb-1 text-[11px] text-term-text">
              <input type="checkbox" checked={rule.track_outcome}
                onChange={(e) => set({ track_outcome: e.target.checked })} />
              Track outcome
            </label>
          </div>

          {error && <div className="text-[11px] text-term-red">{error}</div>}
          <div className="flex justify-end gap-2">
            <button className="btn" onClick={onClose}>Cancel</button>
            <button className="btn-accent" disabled={!rule.name || save.isPending} onClick={() => save.mutate()}>
              Save rule
            </button>
          </div>
        </div>
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
