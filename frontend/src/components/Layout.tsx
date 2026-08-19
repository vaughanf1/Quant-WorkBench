import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, BellRing, Database, FlaskConical, LayoutGrid, Radar, X } from "lucide-react";
import { api, QK } from "@/lib/api";
import { connectAlertStream, dismissToast, useStreamStatus, useToasts } from "@/lib/alertStream";
import { cn } from "@/lib/cn";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutGrid },
  { to: "/screener", label: "Screener", icon: Radar },
  { to: "/backtest", label: "Backtest", icon: FlaskConical },
  { to: "/monitor", label: "Monitor", icon: BellRing },
  { to: "/data", label: "Data", icon: Database },
];

const SEVERITY_BAR: Record<string, string> = {
  info: "bg-term-cyan",
  warn: "bg-term-amber",
  critical: "bg-term-red",
};

export default function Layout() {
  useEffect(() => {
    connectAlertStream();
  }, []);
  const status = useStreamStatus();
  const toasts = useToasts();
  const { data: ds } = useQuery({ queryKey: QK.dataStatus, queryFn: api.dataStatus, refetchInterval: 15_000 });

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-44 shrink-0 flex-col border-r border-term-border bg-term-bg2">
        <div className="flex h-12 items-center border-b border-term-border px-3">
          <span className="text-[13px] font-bold tracking-[0.08em] text-term-amber">QUANT/WB</span>
          <span className="caret" aria-hidden />
        </div>
        <nav className="flex-1 py-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "relative flex items-center gap-2.5 px-3 py-2 text-[11px] uppercase tracking-[0.12em] transition-colors",
                  isActive
                    ? "text-term-amber bg-term-amberSubtle before:absolute before:inset-y-1 before:left-0 before:w-[2px] before:bg-term-amber"
                    : "text-term-muted hover:text-term-text",
                )
              }
            >
              <Icon size={13} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-term-border p-3 text-[10px] leading-relaxed text-term-muted">
          <div className="sub-header mb-1">Universe</div>
          <div className="num text-term-text">{ds?.universe_size ?? "—"} US equities</div>
          <div className="num">EOD {ds?.latest_enriched ?? "—"}</div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-term-border bg-term-bg2 px-4">
          <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.14em] text-term-muted">
            <span>US Equities · S&P 500</span>
            {ds?.pipeline.state === "running" && (
              <span className="amber">
                pipeline {ds.pipeline.pct}% — {ds.pipeline.stage}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em]">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                status === "connected" ? "bg-term-green" : "bg-term-red animate-pulse",
              )}
            />
            <span className={status === "connected" ? "text-term-green" : "text-term-red"}>
              {status === "connected" ? "LIVE" : "RECONNECTING"}
            </span>
          </div>
        </header>

        <main className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3">
          <Outlet />
        </main>
      </div>

      {/* toast layer */}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map(({ id, alert }) => (
          <div
            key={id}
            className="pointer-events-auto flex items-stretch overflow-hidden border border-term-border bg-term-panel shadow-panel"
          >
            <div className={cn("w-1 shrink-0", SEVERITY_BAR[alert.severity] ?? "bg-term-cyan")} />
            <div className="flex-1 px-2.5 py-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-[0.14em] text-term-amber">{alert.rule_name}</span>
                <button
                  onClick={() => dismissToast(id)}
                  className="text-term-muted hover:text-term-text"
                  aria-label="Dismiss alert"
                >
                  <X size={12} />
                </button>
              </div>
              <div className="mt-0.5 text-[12px] text-term-heading">{alert.message}</div>
            </div>
          </div>
        ))}
      </div>

      {/* subtle activity hint while pipeline runs */}
      {ds?.pipeline.state === "running" && (
        <div className="fixed bottom-4 left-48 z-40 flex items-center gap-2 border border-term-border bg-term-panel px-3 py-1.5 text-[10px] uppercase tracking-[0.14em] text-term-amber">
          <Activity size={12} className="animate-pulse" /> {ds.pipeline.message}
        </div>
      )}
    </div>
  );
}
