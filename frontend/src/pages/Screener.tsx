import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Sparkles, Trash2, X } from "lucide-react";
import {
  api, QK,
  type CustomSignal, type ScreenerResult, type SignalCondition, type StrategyMeta,
} from "@/lib/api";
import { dirClass, fmtNum, fmtPct, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/cn";

export default function Screener() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = searchParams.get("strategy");
  const selectedCustom = searchParams.get("signal");
  const [builderOpen, setBuilderOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);

  const { data: strategies } = useQuery({ queryKey: QK.strategies, queryFn: api.strategies });
  const { data: counts } = useQuery({ queryKey: QK.screenerAll, queryFn: api.screenerAll, refetchInterval: 120_000 });
  const { data: customs } = useQuery({ queryKey: QK.customSignals, queryFn: api.customSignals });

  const select = (id: string | null, custom = false) => {
    const next = new URLSearchParams();
    if (id) next.set(custom ? "signal" : "strategy", id);
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-3">
      <section className="panel">
        <div className="panel-header">
          <span>Strategy pool — {counts?.date ?? "…"}</span>
          <div className="flex items-center gap-2 normal-case tracking-normal">
            <button className="btn h-6 px-2 py-0" onClick={() => setBuilderOpen(true)}>
              <Plus size={11} /> Custom signal
            </button>
            <button className="btn h-6 px-2 py-0" onClick={() => setAiOpen(true)}>
              <Sparkles size={11} /> AI strategy
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 p-2.5">
          {strategies?.strategies.map((s) => (
            <StrategyCard key={s.id} meta={s} count={counts?.counts[s.id]}
              active={selected === s.id} onClick={() => select(selected === s.id ? null : s.id)} />
          ))}
          {customs?.signals.map((s) => (
            <CustomSignalCard key={s.id} signal={s} active={selectedCustom === s.id}
              onClick={() => select(selectedCustom === s.id ? null : s.id, true)} />
          ))}
        </div>
        {strategies && strategies.load_errors.length > 0 && (
          <div className="border-t border-term-borderSoft px-2.5 py-1.5 text-[10px] text-term-red">
            {strategies.load_errors.map((e, i) => (
              <div key={i}>{e.file}: {e.error}</div>
            ))}
          </div>
        )}
      </section>

      {selected && <ResultsTable strategyId={selected}
        meta={strategies?.strategies.find((s) => s.id === selected)} />}
      {selectedCustom && <CustomResultsTable signalId={selectedCustom} />}
      {!selected && !selectedCustom && (
        <div className="p-6 text-center font-sans text-[11px] text-term-muted">
          Select a strategy card to screen the universe on today&apos;s enriched data.
        </div>
      )}

      {builderOpen && <SignalBuilderDialog onClose={() => setBuilderOpen(false)} />}
      {aiOpen && <AiBuilderDialog onClose={() => setAiOpen(false)} />}
    </div>
  );
}

/* ---- cards -------------------------------------------------------------- */
function StrategyCard({ meta, count, active, onClick }: {
  meta: StrategyMeta; count?: number; active: boolean; onClick: () => void;
}) {
  return (
    <button onClick={onClick}
      className={cn(
        "flex w-56 flex-col gap-1 border p-2 text-left transition-colors rounded-sm",
        active ? "border-term-accent bg-term-accentSubtle" : "border-term-border bg-term-panel2 hover:border-term-accentDim",
      )}>
      <div className="flex items-center justify-between">
        <span className={cn("text-[11px] font-semibold", active ? "text-term-accent" : "text-term-heading")}>
          {meta.name}
        </span>
        <span className={cn("num text-[13px]", (count ?? 0) > 0 ? "text-term-accent" : "text-term-muted")}>
          {count == null ? "…" : count < 0 ? "ERR" : count}
        </span>
      </div>
      <span className="line-clamp-2 font-sans text-[10px] leading-snug text-term-muted">{meta.description}</span>
      <div className="mt-auto flex gap-1">
        {meta.tags.map((t) => (
          <span key={t} className="tag border-term-border text-term-muted">{t}</span>
        ))}
        {meta.source !== "builtin" && (
          <span className="tag border-term-cyan text-term-cyan">{meta.source}</span>
        )}
      </div>
    </button>
  );
}

function CustomSignalCard({ signal, active, onClick }: {
  signal: CustomSignal; active: boolean; onClick: () => void;
}) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.deleteCustomSignal(signal.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.customSignals }),
  });
  return (
    <div className={cn(
      "relative flex w-56 flex-col gap-1 border p-2 rounded-sm",
      active ? "border-term-cyan bg-term-cyan/5" : "border-term-border bg-term-panel2 hover:border-term-cyan/60",
    )}>
      <button onClick={onClick} className="text-left">
        <div className="text-[11px] font-semibold text-term-cyan">{signal.name || signal.id}</div>
        <div className="mt-1 font-sans text-[10px] leading-snug text-term-muted">
          {signal.conditions.map((c) => `${c.left} ${c.op} ${String(c.right).replace("field:", "")}`).join(" AND ")}
        </div>
      </button>
      <div className="flex items-center justify-between">
        <span className="tag border-term-cyan text-term-cyan">custom signal</span>
        <button onClick={() => del.mutate()} aria-label={`Delete ${signal.id}`}
          className="text-term-muted hover:text-term-red"><Trash2 size={12} /></button>
      </div>
    </div>
  );
}

/* ---- results ------------------------------------------------------------- */
function HitsTable({ result, extraCol }: { result?: ScreenerResult; extraCol?: string }) {
  if (!result) return <div className="p-4 text-[11px] text-term-muted">Screening…</div>;
  if (result.error) return <div className="p-4 text-[11px] text-term-red">{result.error}</div>;
  if (result.hits.length === 0)
    return <div className="p-4 font-sans text-[11px] text-term-muted">No hits on {result.date}.</div>;
  return (
    <div className="scroll-thin max-h-[480px] overflow-auto">
      <table className="grid-data">
        <thead>
          <tr>
            <th>#</th><th>Sym</th><th className="text-right">Last</th><th className="text-right">Chg</th>
            <th className="text-right">RSI14</th><th className="text-right">Mom 20d</th>
            <th className="text-right">Vol×</th><th className="text-right">vs 52wH</th>
            {extraCol && <th className="text-right">{extraCol.replaceAll("_", " ")}</th>}
          </tr>
        </thead>
        <tbody>
          {result.hits.map((h, i) => (
            <tr key={h.symbol}>
              <td className="text-term-muted">{i + 1}</td>
              <td className="font-semibold text-term-heading">{h.symbol}</td>
              <td className="text-right">{fmtPrice(h.close)}</td>
              <td className={cn("text-right", dirClass(h.ret_1d))}>{fmtPct(h.ret_1d)}</td>
              <td className="text-right">{fmtNum(h.rsi14, 1)}</td>
              <td className={cn("text-right", dirClass(h.mom_20d))}>{fmtPct(h.mom_20d, 1)}</td>
              <td className="text-right text-term-muted">{fmtNum(h.vol_ratio_20, 1)}</td>
              <td className="text-right text-term-muted">{fmtPct(h.dist_52w_high, 1)}</td>
              {extraCol && (
                <td className="text-right text-term-cyan">
                  {typeof h[extraCol] === "number" ? fmtNum(h[extraCol] as number, 3) : String(h[extraCol] ?? "—")}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultsTable({ strategyId, meta }: { strategyId: string; meta?: StrategyMeta }) {
  const { data } = useQuery({
    queryKey: QK.screenerRun(strategyId),
    queryFn: () => api.screenerRun(strategyId),
  });
  const extra = meta?.order_by && !["ret_1d", "rsi14", "mom_20d", "vol_ratio_20", "dist_52w_high"].includes(meta.order_by)
    ? meta.order_by : undefined;
  return (
    <section className="panel">
      <div className="panel-header">
        <span>{meta?.name ?? strategyId} — {data?.count ?? "…"} hits</span>
        {meta && (
          <span className="normal-case tracking-normal text-term-muted">
            stop {meta.stop_loss != null ? fmtPct(meta.stop_loss, 0) : "—"} · hold ≤{meta.max_hold_days ?? "—"}d ·
            ranked by {meta.order_by ?? "—"}
          </span>
        )}
      </div>
      <HitsTable result={data} extraCol={extra} />
    </section>
  );
}

function CustomResultsTable({ signalId }: { signalId: string }) {
  const { data } = useQuery({
    queryKey: QK.screenerCustom(signalId),
    queryFn: () => api.screenerCustom(signalId),
  });
  return (
    <section className="panel">
      <div className="panel-header">Custom signal · {signalId} — {data?.count ?? "…"} hits</div>
      <HitsTable result={data} />
    </section>
  );
}

/* ---- custom signal builder dialog ----------------------------------------- */
const EMPTY_COND: SignalCondition = { left: "close", op: ">", right: "field:ma20", leftDays: 0, rightDays: 0 };

function SignalBuilderDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: options } = useQuery({ queryKey: QK.signalOptions, queryFn: api.signalOptions });
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [conditions, setConditions] = useState<SignalCondition[]>([{ ...EMPTY_COND }]);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api.saveCustomSignal({ id, name, enabled: true, conditions }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.customSignals });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const patch = (i: number, p: Partial<SignalCondition>) =>
    setConditions((cs) => cs.map((c, j) => (j === i ? { ...c, ...p } : c)));

  const idValid = /^[a-z0-9_]{1,40}$/.test(id);

  return (
    <Dialog title="Custom signal builder" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className="sub-header">Signal id (a–z, 0–9, _)</span>
            <input className="input" value={id} onChange={(e) => setId(e.target.value)} placeholder="cheap_momentum" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="sub-header">Display name</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Cheap momentum" />
          </label>
        </div>

        <div className="flex flex-col gap-2">
          <span className="sub-header">Conditions (all must hold — AND)</span>
          {conditions.map((c, i) => (
            <ConditionRow key={i} cond={c} options={options} onPatch={(p) => patch(i, p)}
              onRemove={conditions.length > 1 ? () => setConditions((cs) => cs.filter((_, j) => j !== i)) : undefined} />
          ))}
          {conditions.length < (options?.maxConditions ?? 8) && (
            <button className="btn self-start" onClick={() => setConditions((cs) => [...cs, { ...EMPTY_COND }])}>
              <Plus size={11} /> Add condition
            </button>
          )}
        </div>

        {error && <div className="text-[11px] text-term-red">{error}</div>}
        <div className="flex justify-end gap-2">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn-accent" disabled={!idValid || save.isPending} onClick={() => save.mutate()}>
            Save signal
          </button>
        </div>
      </div>
    </Dialog>
  );
}

function ConditionRow({ cond, options, onPatch, onRemove }: {
  cond: SignalCondition;
  options?: { groups: Record<string, string[]>; operators: string[]; maxDays: number };
  onPatch: (p: Partial<SignalCondition>) => void;
  onRemove?: () => void;
}) {
  const isField = String(cond.right).startsWith("field:");
  const fieldSelect = (value: string, onChange: (v: string) => void) => (
    <select className="input w-44" value={value} onChange={(e) => onChange(e.target.value)}>
      {options && Object.entries(options.groups).map(([group, fields]) => (
        <optgroup key={group} label={group}>
          {fields.map((f) => <option key={f} value={f}>{f}</option>)}
        </optgroup>
      ))}
    </select>
  );
  return (
    <div className="flex flex-wrap items-center gap-1.5 border border-term-borderSoft bg-term-bg2 p-1.5 rounded-sm">
      {fieldSelect(cond.left, (v) => onPatch({ left: v }))}
      <DaysInput value={cond.leftDays} max={options?.maxDays ?? 60} onChange={(v) => onPatch({ leftDays: v })} />
      <select className="input w-14" value={cond.op} onChange={(e) => onPatch({ op: e.target.value })}>
        {(options?.operators ?? [">", ">=", "<", "<=", "==", "!="]).map((op) => (
          <option key={op} value={op}>{op}</option>
        ))}
      </select>
      <select className="input w-20" value={isField ? "field" : "number"}
        onChange={(e) => onPatch({ right: e.target.value === "field" ? "field:ma20" : "0" })}>
        <option value="number">number</option>
        <option value="field">field</option>
      </select>
      {isField ? (
        <>
          {fieldSelect(String(cond.right).slice(6), (v) => onPatch({ right: `field:${v}` }))}
          <DaysInput value={cond.rightDays} max={options?.maxDays ?? 60} onChange={(v) => onPatch({ rightDays: v })} />
        </>
      ) : (
        <input className="input w-24" value={String(cond.right)}
          onChange={(e) => onPatch({ right: e.target.value })} placeholder="0.05" />
      )}
      {onRemove && (
        <button onClick={onRemove} className="ml-auto text-term-muted hover:text-term-red" aria-label="Remove condition">
          <X size={12} />
        </button>
      )}
    </div>
  );
}

function DaysInput({ value, max, onChange }: { value: number; max: number; onChange: (v: number) => void }) {
  return (
    <label className="flex items-center gap-1 text-[10px] text-term-muted">
      <input type="number" min={0} max={max} className="input w-14" value={value}
        onChange={(e) => onChange(Math.max(0, Math.min(max, Number(e.target.value) || 0)))} />
      d ago
    </label>
  );
}

/* ---- AI strategy builder ---------------------------------------------------- */
function AiBuilderDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [description, setDescription] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const gen = useMutation({
    mutationFn: () => api.generateStrategy(description),
    onSuccess: (r) => {
      setCode(r.code);
      setError(r.valid ? null : r.error);
    },
    onError: (e: Error) => setError(e.message),
  });
  const save = useMutation({
    mutationFn: () => api.saveStrategyCode(code!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.strategies });
      qc.invalidateQueries({ queryKey: QK.screenerAll });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Dialog title="AI strategy builder" onClose={onClose} wide>
      <div className="flex flex-col gap-3">
        <p className="font-sans text-[11px] leading-relaxed text-term-muted">
          Describe the setup in plain language. The generated file is validated with an AST allowlist
          (polars-only imports, no I/O) before it can be saved, and re-validated on every load.
        </p>
        <textarea className="input h-20 font-sans" value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. Stocks within 5% of their 52-week high whose 20-day volume ratio is above 1.5, ranked by 60-day momentum" />
        <div className="flex gap-2">
          <button className="btn-accent" disabled={!description.trim() || gen.isPending} onClick={() => gen.mutate()}>
            <Sparkles size={11} /> {gen.isPending ? "Generating…" : "Generate"}
          </button>
          {code && !error && (
            <button className="btn" disabled={save.isPending} onClick={() => save.mutate()}>
              Save to strategy pool
            </button>
          )}
        </div>
        {error && <div className="text-[11px] text-term-red">{error}</div>}
        {code && (
          <pre className="scroll-thin max-h-72 overflow-auto border border-term-borderSoft bg-term-bg2 p-2 text-[11px] leading-relaxed text-term-text">
            {code}
          </pre>
        )}
      </div>
    </Dialog>
  );
}

/* ---- shared dialog shell --------------------------------------------------- */
function Dialog({ title, onClose, wide, children }: {
  title: string; onClose: () => void; wide?: boolean; children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className={cn("panel max-h-[85vh] w-full overflow-y-auto scroll-thin shadow-panel", wide ? "max-w-3xl" : "max-w-xl")}
        onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <span>{title}</span>
          <button onClick={onClose} className="text-term-muted hover:text-term-text" aria-label="Close dialog">
            <X size={13} />
          </button>
        </div>
        <div className="p-3">{children}</div>
      </div>
    </div>
  );
}
