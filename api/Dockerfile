# Built from the repository root (see deploy/docker-compose.yml), so the image also holds
# data/ and policy/, which the loaders and the engine read.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/api

COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY data /app/data
COPY policy /app/policy
COPY api .
ENV PATH="/app/api/.venv/bin:$PATH"

EXPOSE 8000
# Migrations run on every start, so a laptop and the VM reach the same schema.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
