# Production web build — output is a static site served by Caddy.
# This Dockerfile is NOT used in local dev (run `npm run dev` locally).

# ---- Build stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests first for better layer caching
COPY apps/web/package.json apps/web/package-lock.json* ./

RUN npm ci --prefer-offline

# Copy source
COPY apps/web/ .

# Build static assets
RUN npm run build

# ---- Distribution stage ----
# Keep dist outside /app: the base compose service bind-mounts source at /app.
# This image copies the build into the web_dist volume; Caddy serves that volume.
FROM node:20-alpine AS dist

WORKDIR /opt/dist

COPY --from=builder /app/dist .
COPY infra/docker/web-dist-sync.sh /usr/local/bin/web-dist-sync
RUN chmod +x /usr/local/bin/web-dist-sync

# One-shot volume population for the production compose overlay.
# The script publishes assets first and index.html last so an interrupted
# sync never leaves the live site empty (review finding: rm-rf-first swap
# had a window where /assets/* misses could be cached as immutable).
CMD ["web-dist-sync"]
