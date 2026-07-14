FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first to leverage layer cache
COPY pyproject.toml ./
COPY apps/ apps/
COPY scripts/ scripts/
COPY packages/ packages/
COPY config/ config/

# Install production dependencies with uv (no dev extras)
RUN uv pip install --system --no-cache .

# P0-4 — build provenance (after the dep layer: cache-safe).
ARG GIT_SHA=unknown
ARG GIT_BRANCH=unknown
ARG GIT_DIRTY=unknown
ARG BUILD_TS=unknown
ENV GIT_SHA=$GIT_SHA \
    GIT_BRANCH=$GIT_BRANCH \
    GIT_DIRTY=$GIT_DIRTY \
    BUILD_TS=$BUILD_TS
LABEL org.arthos.git_sha=$GIT_SHA \
      org.arthos.git_branch=$GIT_BRANCH \
      org.arthos.git_dirty=$GIT_DIRTY \
      org.arthos.build_ts=$BUILD_TS

CMD ["python", "-m", "apps.worker.src.main"]
