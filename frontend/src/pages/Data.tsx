import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { api, QK } from "@/lib/api";
import { dirClass, fmtPct, fmtPrice } from "@/lib/format";
import Spark from "@/components/Spark";
import { cn } from "@/lib/cn";

export default function Data() {
  const qc = useQueryClient();
  const { data: ds } = useQuery({
    queryKey: QK.dataStatus, queryFn: api.dataStatus,
    refetchInterval: (q) => (q.state.data?.pipeline.state === "running" ? 2_000 : 15_000),
  });
  const run = useMutation({
    mutationFn: () => api.runPipeline(30),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.dataStatus }),
  });
  const p = ds?.pipeline;

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-3">
      <section className="panel">
        <div className="panel-header">
          <span>Post-market pipeline</span>
          <button className="btn h-6 px-2 py-0 normal-case tracking-normal"
            disabled={p?.state === "running" || run.isPending} onClick={() => run.mutate()}>
            <RefreshCw size={11} className={p?.state === "running" ? "animate-spin" : ""} />
            {p?.state === "running" ? "Running…" : "Run now"}
          </button>
        </div>
        <div className="flex flex-col gap-2 p-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Cell label="Universe" value={`${ds?.universe_size ?? "—"} tickers`} />
            <Cell label="Enriched through" value={ds?.latest_enriched ?? "—"} />
            <Cell label="Symbols enriched" value={String(ds?.symbols ?? "—")} />
            <Cell label="Last run" value={p?.last_run ?? "never this session"} />
          </div>
          {p?.state === "running" && (
            <div>
              <div className="h-2 w-full overflow-hidden rounded-sm bg-term-bg2">
                <div className="h-full bg-term-accent transition-all" style={{ width: `${p.pct}%` }} />
              </div>
              <div className="mt-1 text-[10px] text-term-muted">
                {p.stage} — {p.message}
              </div>
            </div>
          )}
          {p && p.errors.length > 0 && (
            <div className="text-[10px] text-term-red">
              {p.errors.map((e, i) => <div key={i}>{e}</div>)}
            </div>
          )}
          <p className="font-sans text-[10px] leading-relaxed text-term-muted">
            Scheduled weekdays at 17:30 New York time: pulls EOD bars via OpenBB, rebuilds the enriched
            indicator tables, resolves tracked signal outcomes, then evaluates monitor rules.
          </p>
        </div>
      </section>

      <SymbolInspector />
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="sub-header">{label}</div>
      <div className="num mt-0.5 text-[13px] text-term-heading">{value}</div>
    </div>
  );
}

/* quick per-symbol sanity view over the cached bars */
function SymbolInspector() {
  const [input, setInput] = useState("AAPL");
  const [symbol, setSymbol] = useState("AAPL");
  const { data, error } = useQuery({
    queryKey: QK.candles(symbol),
    queryFn: () => api.candles(symbol, 250),
    retry: 0,
  });
  const bars = data?.bars ?? [];
  const last = bars.at(-1);
  const prev = bars.at(-2);
  const ret = last && prev ? last.close / prev.close - 1 : null;

  return (
    <section className="panel">
      <div className="panel-header">
        <span>Symbol inspector</span>
        <form className="flex items-center gap-1 normal-case tracking-normal"
          onSubmit={(e) => { e.preventDefault(); setSymbol(input.trim().toUpperCase()); }}>
          <input className="input h-6 w-24" value={input} onChange={(e) => setInput(e.target.value)} />
          <button className="btn h-6 px-2 py-0" type="submit" aria-label="Look up symbol">
            <Search size={11} />
          </button>
        </form>
      </div>
      {error ? (
        <div className="p-4 text-[11px] text-term-red">No cached bars for {symbol}. Run the pipeline first.</div>
      ) : (
        <div className="flex flex-wrap items-center gap-6 p-3">
          <div>
            <div className="text-[15px] font-semibold text-term-heading">{data?.symbol}</div>
            <div className="flex items-baseline gap-2">
              <span className="num text-lg text-term-heading">{fmtPrice(last?.close)}</span>
              <span className={cn(dirClass(ret))}>{fmtPct(ret)}</span>
            </div>
            <div className="num text-[10px] text-term-muted">
              {bars.length} bars · {bars[0]?.date} → {last?.date}
            </div>
          </div>
          <Spark values={bars.map((b) => b.close)} width={420} height={80} />
        </div>
      )}
    </section>
  );
}
