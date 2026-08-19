/** Global SSE channel (/api/stream) + module-level toast queue.
 * One EventSource mounted once in Layout; toasts auto-dismiss and batch. */
import { useSyncExternalStore } from "react";
import type { Alert } from "@/lib/api";

export interface ToastItem {
  id: number;
  alert: Alert;
}

export type StreamStatus = "connecting" | "connected" | "reconnecting";

let toasts: ToastItem[] = [];
let status: StreamStatus = "connecting";
let nextId = 1;
let es: EventSource | null = null;
let backoff = 1000;
const listeners = new Set<() => void>();
const AUTO_DISMISS = 6000;
const MAX_TOASTS = 4;

function emit() {
  toasts = [...toasts];
  listeners.forEach((l) => l());
}

export function pushToasts(alerts: Alert[]) {
  for (const alert of alerts.slice(0, MAX_TOASTS)) {
    const id = nextId++;
    toasts.push({ id, alert });
    setTimeout(() => dismissToast(id), AUTO_DISMISS);
  }
  toasts = toasts.slice(-MAX_TOASTS);
  emit();
}

export function dismissToast(id: number) {
  const before = toasts.length;
  toasts = toasts.filter((t) => t.id !== id);
  if (toasts.length !== before) emit();
}

let statusSnapshot: { status: StreamStatus } = { status };
function setStatus(s: StreamStatus) {
  if (status === s) return;
  status = s;
  statusSnapshot = { status };
  listeners.forEach((l) => l());
}

export function connectAlertStream() {
  if (es) return;
  const open = () => {
    es = new EventSource("/api/stream");
    es.onopen = () => {
      backoff = 1000;
      setStatus("connected");
    };
    es.addEventListener("alerts", (e) => {
      const alerts = JSON.parse((e as MessageEvent).data) as Alert[];
      pushToasts(alerts);
    });
    es.onerror = () => {
      es?.close();
      es = null;
      setStatus("reconnecting");
      backoff = Math.min(backoff * 2, 30000);
      setTimeout(open, backoff);
    };
  };
  open();
}

export function useToasts(): ToastItem[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => toasts,
    () => toasts,
  );
}

export function useStreamStatus(): StreamStatus {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => statusSnapshot.status,
    () => "connecting" as StreamStatus,
  );
}
