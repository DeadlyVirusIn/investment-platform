FROM python:3.12-slim

# ---- system deps ----
# supercronic: user-space cron that prints jobs' stdout/stderr to container
# logs (no sendmail/syslog needed), handles signals, single-process.
ENV SUPERCRONIC_VERSION=v0.2.29
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates tzdata util-linux \
    && curl -fsSLo /usr/local/bin/supercronic \
       "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# ---- uv for fast pip installs ----
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first to leverage layer cache
COPY pyproject.toml ./
COPY apps/ apps/
COPY scripts/ scripts/
COPY packages/ packages/
COPY infra/alembic/ infra/alembic/
# Feature registry yaml + any runtime config
COPY config/ config/

# Install production dependencies with uv (no dev extras)
RUN uv pip install --system --no-cache .

# Scheduler artifacts
COPY infra/docker/worker.crontab /app/crontab
RUN chmod +x /app/scripts/run_daily_loop.sh

# Default timezone (overridable via compose TZ env)
ENV TZ=America/New_York

# supercronic = PID 1: handles signals, forwards stdout/stderr to container.
CMD ["supercronic", "-quiet", "/app/crontab"]
