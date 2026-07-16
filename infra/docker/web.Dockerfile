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

# One-shot volume population for the production compose overlay.
CMD ["sh", "-c", "rm -rf /srv/web/* && cp -a /opt/dist/. /srv/web/ && echo 'web dist synced'"]
