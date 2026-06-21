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

# Test deps for CI / test images ONLY. Default false -> the production runtime
# image never includes pytest. Build the test image with
# `--build-arg INSTALL_TEST_DEPS=true` to run the integration suite reliably.
ARG INSTALL_TEST_DEPS=false
RUN if [ "$INSTALL_TEST_DEPS" = "true" ]; then \
        uv pip install --system --no-cache pytest pytest-asyncio; \
    fi

# P0-4 — build provenance (after the dep layer: cache-safe).
# Supplied by compose build args / Makefile; defaults flag as unknown_sha.
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

# Expose API port
EXPOSE 8000

CMD ["uvicorn", "apps.api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
