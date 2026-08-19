#!/usr/bin/env bash
# Start backend (uvicorn --reload, :3018) and frontend (vite, :3011) together.
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
command -v pnpm >/dev/null || { echo "pnpm is required: corepack enable"; exit 1; }

free_port() {
  local pids
  pids=$(lsof -ti:"$1" 2>/dev/null || true)
  [ -n "$pids" ] && { echo "freeing port $1"; kill $pids 2>/dev/null || true; sleep 1; }
}
free_port 3018
free_port 3011

[ -d backend/.venv ] || (cd backend && uv sync)
[ -d frontend/node_modules ] || (cd frontend && pnpm install)

cleanup() { kill 0 2>/dev/null; }
trap cleanup INT TERM EXIT

(cd backend && uv run --no-sync uvicorn app.main:app --reload --port 3018 2>&1 \
  | awk '{print "\033[33m[api]\033[0m " $0; fflush()}') &
(cd frontend && pnpm dev 2>&1 \
  | awk '{print "\033[36m[ui] \033[0m " $0; fflush()}') &

echo "API  http://127.0.0.1:3018    UI  http://127.0.0.1:3011"
wait
