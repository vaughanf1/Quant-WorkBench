# ---- frontend build ----------------------------------------------------------
FROM node:22-slim AS ui
WORKDIR /ui
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ .
RUN pnpm build

# ---- backend runtime ----------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend/ backend/
COPY --from=ui /ui/dist frontend/dist
ENV DATA_DIR=/app/data PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 3018
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3018"]
