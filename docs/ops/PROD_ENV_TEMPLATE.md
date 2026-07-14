# Production `.env` Template (M6B)

Redacted template for the prod/Oracle `.env`. **Placeholders only — never commit
real secrets.** Create this file on the host (not in git). After filling it, run
`make public-beta-preflight-prod` — it must return OK / exit 0 before deploy.

## Required — core + auth (deploy blocks without these)

```sh
# Postgres (use a STRONG random password, not the dev one)
POSTGRES_USER=invest_prod
POSTGRES_PASSWORD=<STRONG_RANDOM_PASSWORD>
POSTGRES_DB=investment_platform
DATABASE_URL=postgresql+psycopg://invest_prod:<STRONG_RANDOM_PASSWORD>@db:5432/investment_platform

# Secret encryption — ROTATE; generate fresh, never reuse the dev key:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=<ROTATED_FERNET_KEY>

# Core market data — REQUIRED for paper pricing
TIINGO_API_KEY=<REQUIRED_TIINGO_KEY>

# Auth / session — EXACT safe production values
AUTH_DISABLED_LOCAL=false        # real accounts only (dev ships true)
DEMO_DEVICE_MODE=false           # device-header identity is demo-only
SESSION_COOKIE_SECURE=true       # requires real HTTPS at the edge

# CORS — the SPA origin Caddy/Cloudflare serves the frontend from. Never '*'.
CORS_ALLOWED_ORIGINS=https://<your-spa-domain>

# Trusted proxy (login rate-limiting reads the real client IP behind Caddy/CF)
AUTH_TRUST_PROXY_HEADERS=true
AUTH_TRUSTED_PROXY_CIDRS=<ingress-or-cloudflare-CIDRs>   # e.g. 172.16.0.0/12 and/or CF ranges

APP_VERSION=1.0.0-beta
LOG_LEVEL=INFO
```

## Optional providers (graceful-degrade if absent)

```sh
# FRED — recommended (macro stage of the daily pipeline)
FRED_API_KEY=<optional>
# Polygon — company names / earnings / news
POLYGON_API_KEY=<optional>
# Benzinga — news + sentiment
BENZINGA_API_KEY=<optional>
# Finnhub — catalysts/news. ROTATE the previously-exposed key, or OMIT entirely.
# FINNHUB_API_KEY=<rotated-or-omit>
# SEC EDGAR — free, no key; set a contact User-Agent for prod
SEC_EDGAR_USER_AGENT="ArthOS ops@your-domain"
# Options are paper-only + dormant by default; keep the kill switches:
OPTIONS_ENABLED=false
OPTIONS_PAPER_ONLY=true
# Tradier (sandbox) only if options are exercised:
# TRADIER_ACCESS_TOKEN=<optional-sandbox>
```

## Notes

- **HTTPS is required** for `SESSION_COOKIE_SECURE=true`. The current `Caddyfile`
  listens on `:80` only with no domain block — either (a) add a `your-domain { … }`
  block for Caddy ACME auto-HTTPS, or (b) put Cloudflare in front (TLS at CF,
  Caddy stays `:80` behind it) and set `AUTH_TRUST_PROXY_HEADERS` + the CF CIDRs.
- Do **not** print or commit any of these values. Keep the prod `.env` host-only
  (e.g. `~/investment-platform/.env`, `chmod 600`).
- Generate the Postgres password + FERNET_KEY fresh; never reuse `dev_only_password`
  or the dev FERNET key.
