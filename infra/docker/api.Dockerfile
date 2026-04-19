FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first to leverage layer cache
COPY pyproject.toml ./
COPY apps/ apps/
COPY scripts/ scripts/
COPY packages/ packages/
COPY infra/alembic/ infra/alembic/

# Install production dependencies with uv (no dev extras)
RUN uv pip install --system --no-cache .

# Expose API port
EXPOSE 8000

CMD ["uvicorn", "apps.api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
