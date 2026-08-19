import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, QK, type Dashboard as Dash } from "@/lib/api";
import { dirClass, fmtPct, fmtPrice, fmtNum } from "@/lib/format";
import Spark from "@/components/Spark";
import { cn } from "@/lib/cn";

export default function Dashboard() {
  const { data, isLoading } = useQuery({ queryKey: QK.dashboard, queryFn: api.dashboard, refetchInterval: 60_000 });

  if (isLoading) return <PageEmpty text="Loading market state…" />;
  if (!data?.date)
    return (
      <PageEmpty text="No enriched data yet. Run the data pipeline to pull EOD bars and compute indicators.">
        <Link to="/data" className="btn-accent mt-3">Open data page</Link>
      </PageEmpty>
    );

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-3">
      <BreadthTape data={data} />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <MoversPanel title="Top gainers" rows={data.gainers} />
        <MoversPanel title="Top losers" rows={data.losers} />
        <SectorPanel sectors={data.sectors} />
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <StrategyPulse counts={data.strategy_counts} />
        <AlertsPanel alerts={data.alerts} />
        <ScorecardPanel cards={data.scorecards} />
      </div>
    </div>
  );
}

/* ---- hero: the market breadth tape ------------------------------------- */
function BreadthTape({ data }: { data: Dash }) {
  const b = data.breadth;
  const unch = Math.max(0, b.total - b.advancers - b.decliners);
  const pct = (n: number) => (b.total ? (n / b.total) * 100 : 0);
  const spy = data.spy;
  const spyLast = spy.at(-1)?.close;
  const spyPrev = spy.at(-2)?.close;
  const spyRet = spyLast && spyPrev ? spyLast / spyPrev - 1 : null;
  const above = pct(b.above_ma200);

  return (
    <section className="panel">
      <div className="panel-header">
        <span>Market tape — {data.date}</span>
        <span className="normal-case tracking-normal text-term-muted">EOD close</span>
      </div>
      <div className="grid grid-cols-1 gap-4 p-3 md:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          {/* segmented advance/decline bar */}
          <div className="flex h-8 w-full overflow-hidden rounded-sm border border-term-borderSoft">
            <div className="h-full bg-term-greenDim/60" style={{ width: `${pct(b.advancers)}%` }} />
            <div className="h-full bg-term-panel2" style={{ width: `${pct(unch)}%` }} />
            <div className="h-full bg-term-redDim/60" style={{ width: `${pct(b.decliners)}%` }} />
          </div>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <Stat label="Advancers" value={String(b.advancers)} cls="up" />
            <Stat label="Decliners" value={String(b.decliners)} cls="down" />
            <Stat label="Above MA200" value={`${b.above_ma200} · ${above.toFixed(0)}%`}
              cls={above >= 50 ? "up" : "down"} />
            <Stat label="New 52w highs" value={String(b.new_highs_252d)} cls="text-term-heading num" />
            <Stat label="New 60d lows" value={String(b.new_lows_60d)} cls="text-term-heading num" />
          </div>
        </div>
        <div className="flex items-center gap-3 border-term-borderSoft md:border-l md:pl-4">
          <div>
            <div className="sub-header">SPY · 120d</div>
            <div className="flex items-baseline gap-2">
              <span className="num text-lg text-term-heading">{fmtPrice(spyLast)}</span>
              <span className={dirClass(spyRet)}>{fmtPct(spyRet)}</span>
            </div>
          </div>
          <Spark values={spy.map((p) => p.close)} width={180} height={44} />
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="sub-header">{label}</span>
      <span className={cn("text-[13px]", cls)}>{value}</span>
    </div>
  );
}

/* ---- movers -------------------------------------------------------------- */
function MoversPanel({ title, rows }: { title: string; rows: Dash["gainers"] }) {
  return (
    <section className="panel min-h-[220px]">
      <div className="panel-header">{title}</div>
      <table className="grid-data">
        <thead>
          <tr><th>Sym</th><th className="text-right">Last</th><th className="text-right">Chg</th><th className="text-right">Vol×</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td className="text-term-heading">{r.symbol}</td>
              <td className="text-right">{fmtPrice(r.close)}</td>
              <td className={cn("text-right", dirClass(r.ret_1d))}>{fmtPct(r.ret_1d)}</td>
              <td className="text-right text-term-muted">{fmtNum(r.vol_ratio_20, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/* ---- sectors -------------------------------------------------------------- */
function SectorPanel({ sectors }: { sectors: Dash["sectors"] }) {
  const maxAbs = Math.max(0.001, ...sectors.map((s) => Math.abs(s.avg_ret)));
  return (
    <section className="panel min-h-[220px]">
      <div className="panel-header">Sector day</div>
      <div className="flex flex-col gap-1 p-2">
        {sectors.map((s) => {
          const w = (Math.abs(s.avg_ret) / maxAbs) * 100;
          const upDay = s.avg_ret >= 0;
          return (
            <div key={s.sector} className="flex items-center gap-2 text-[11px]">
              <span className="w-36 truncate text-term-muted">{s.sector}</span>
              <div className="relative h-3 flex-1 overflow-hidden rounded-sm bg-term-bg2">
                <div
                  className={cn("absolute inset-y-0", upDay ? "left-1/2 bg-term-greenDim" : "right-1/2 bg-term-redDim")}
                  style={{ width: `${w / 2}%` }}
                />
                <div className="absolute inset-y-0 left-1/2 w-px bg-term-border" />
              </div>
              <span className={cn("w-14 text-right", dirClass(s.avg_ret))}>{fmtPct(s.avg_ret)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ---- strategy pulse -------------------------------------------------------- */
function StrategyPulse({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <section className="panel min-h-[200px]">
      <div className="panel-header">
        <span>Strategy pulse</span>
        <Link to="/screener" className="normal-case tracking-normal text-term-muted hover:text-term-accent">
          open screener →
        </Link>
      </div>
      <div className="flex flex-col gap-1 p-2">
        {entries.map(([id, n]) => (
          <Link to={`/screener?strategy=${id}`} key={id}
            className="group flex items-center gap-2 text-[11px]">
            <span className="w-40 truncate text-term-muted group-hover:text-term-text">{id.replaceAll("_", " ")}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-sm bg-term-bg2">
              <div className="h-full bg-term-accentDim group-hover:bg-term-accent transition-colors"
                style={{ width: `${(Math.max(n, 0) / max) * 100}%` }} />
            </div>
            <span className={cn("num w-8 text-right", n > 0 ? "text-term-accent" : "text-term-muted")}>
              {n < 0 ? "ERR" : n}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

/* ---- alerts ----------------------------------------------------------------- */
const SEV_TEXT: Record<string, string> = {
  info: "text-term-cyan", warn: "text-term-accent", critical: "text-term-red",
};

function AlertsPanel({ alerts }: { alerts: Dash["alerts"] }) {
  return (
    <section className="panel min-h-[200px]">
      <div className="panel-header">
        <span>Latest alerts</span>
        <Link to="/monitor" className="normal-case tracking-normal text-term-muted hover:text-term-accent">
          monitor →
        </Link>
      </div>
      {alerts.length === 0 ? (
        <EmptyNote text="No alerts recorded yet. Add monitor rules and run a monitor pass." />
      ) : (
        <div className="flex flex-col p-1">
          {alerts.map((a, i) => (
            <div key={i} className="flex items-baseline gap-2 px-1.5 py-1 text-[11px]">
              <span className={cn("tag border-current", SEV_TEXT[a.severity])}>{a.severity}</span>
              <span className="text-term-heading">{a.symbol}</span>
              <span className="truncate text-term-muted">{a.rule_name}</span>
              <span className="ml-auto num text-term-muted">{a.date}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ---- scorecards --------------------------------------------------------------- */
function ScorecardPanel({ cards }: { cards: Dash["scorecards"] }) {
  const c30 = cards.filter((c) => c.period === "30d");
  return (
    <section className="panel min-h-[200px]">
      <div className="panel-header">Signal scorecards · 30d</div>
      {c30.length === 0 ? (
        <EmptyNote text="No resolved outcomes in the last 30 days. Tracked signals appear here once they hit target, stop, or expiry." />
      ) : (
        <table className="grid-data">
          <thead>
            <tr><th>Strategy</th><th className="text-right">N</th><th className="text-right">Win</th><th className="text-right">Avg</th></tr>
          </thead>
          <tbody>
            {c30.map((c) => (
              <tr key={c.strategy_id}>
                <td className="text-term-heading">{c.strategy_id}</td>
                <td className="text-right">{c.n}</td>
                <td className={cn("text-right", c.win_rate >= 0.5 ? "up" : "down")}>{fmtPct(c.win_rate, 0)}</td>
                <td className={cn("text-right", dirClass(c.avg_ret))}>{fmtPct(c.avg_ret)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <div className="p-4 font-sans text-[11px] leading-relaxed text-term-muted">{text}</div>;
}

function PageEmpty({ text, children }: { text: string; children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <div className="font-sans text-[12px] text-term-muted">{text}</div>
      {children}
    </div>
  );
}
