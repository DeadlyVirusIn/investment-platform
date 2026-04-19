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

# ---- Serve stage ----
# Caddy in prod compose mounts web_dist volume from this image's /app/dist.
# We use a minimal image just to hold the files; Caddy serves them.
FROM node:20-alpine AS dist

WORKDIR /app/dist

COPY --from=builder /app/dist .

# This container isn't meant to run a process — Caddy reads the volume.
# If you want a self-contained image, swap to caddy:2-alpine and COPY dist → /srv/web.
CMD ["sh", "-c", "echo 'Static assets ready in /app/dist' && tail -f /dev/null"]
