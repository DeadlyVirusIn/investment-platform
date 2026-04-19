FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first to leverage layer cache
COPY pyproject.toml ./
COPY apps/ apps/
COPY scripts/ scripts/
COPY packages/ packages/

# Install production dependencies with uv (no dev extras)
RUN uv pip install --system --no-cache .

CMD ["python", "-m", "apps.worker.src.main"]
