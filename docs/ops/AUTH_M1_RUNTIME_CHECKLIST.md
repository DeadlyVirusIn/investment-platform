# Auth M1 — Runtime / Production Checklist

**Scope:** operating the M1 account/session auth (commit `2122a48` + M1A hardening). Read before any public/Oracle deploy.

## Required production config

| Setting | Prod value | Why |
|---|---|---|
| `AUTH_DISABLED_LOCAL` | **False** | True falls back to a synthetic dev user + honors the device header — never in prod. |
| `DEMO_DEVICE_MODE` | **False** | True honors the `X-Auth-User-Id` device header as identity — demo/dev only. |
| `SESSION_COOKIE_SECURE` | **True** (behind HTTPS) | Marks the `arthos_session` cookie Secure so it is never sent over plain HTTP. |

**Hard rule:** with both demo flags False, `X-Auth-User-Id` **must never authenticate a public user.** Identity comes only from a valid `arthos_session` cookie; a spoofed header resolves to anonymous (shared demo book for reads, 401 for writes), never a targeted user's private book.

## Required verification before public beta

1. Confirm the three settings above on the running API.
2. Run the spoof-block curl checklist (below) against the prod-config API — all must pass.
3. Confirm `SESSION_COOKIE_SECURE=True` and that login sets a `Secure; HttpOnly; SameSite=Lax` cookie.
4. Add rate-limiting / lockout on `/api/login` (M1A leaves this open — required before public exposure).
5. Confirm the demo device path is **off** (DEMO_DEVICE_MODE=False) in prod; demo verification is dev-only.

## Curl checklist — core session flow (AUTH_DISABLED_LOCAL=False, DEMO_DEVICE_MODE=False)

```sh
B=https://<host>; JA=jarA; JB=jarB
# signup A -> 200 + Set-Cookie arthos_session; body has user (no hash)
curl -s -c $JA -X POST $B/api/signup -H 'Content-Type: application/json' \
  -d '{"email":"a@x.com","password":"password123"}'
# A's own book
curl -s -b $JA $B/api/paper/canonical/stock      # portfolio_id = A's user:<id>:stock
# logout revokes session + clears cookie
curl -s -b $JA -c $JA -X POST $B/api/logout
# login A again -> SAME book (persists)
curl -s -c $JA -X POST $B/api/login -H 'Content-Type: application/json' \
  -d '{"email":"a@x.com","password":"password123"}'
curl -s -b $JA $B/api/paper/canonical/stock      # same portfolio_id as before
# bad password -> 401 generic ("invalid email or password")
curl -s -o /dev/null -w '%{http_code}' -X POST $B/api/login \
  -H 'Content-Type: application/json' -d '{"email":"a@x.com","password":"wrong"}'
```

## Spoofed-header negative test (MUST fail to authenticate)

With `DEMO_DEVICE_MODE=False` + `AUTH_DISABLED_LOCAL=False`:

```sh
# Spoof A's id in the device header, NO session cookie:
curl -s -H "X-Auth-User-Id: <A-user-id>" $B/api/paper/canonical/stock
#   -> shared demo book (CANONICAL_STOCK_PORTFOLIO_ID), NEVER A's private book.
# Unauthenticated write -> 401 (no session, header ignored):
curl -s -o /dev/null -w '%{http_code}' -H "X-Auth-User-Id: <A-user-id>" \
  -X POST $B/api/portfolios/<slug>/follow -H 'Content-Type: application/json' -d '{}'
#   -> 401 (require_user_id rejects: no resolved identity).
# User B's cookie cannot read/mutate A's book (B resolves to B's own portfolio_id only).
```

## Demo-mode-only verification (dev/demo: DEMO_DEVICE_MODE=True)

The seeded demo device must still resolve to the seeded book:

```sh
# device 305fcf0b-... -> book bc207e65-... ; NAV ~$105,211 ; realized ~+$5,952 ; 30 open
curl -s -H "X-Auth-User-Id: 305fcf0b-bc89-4d9d-ba47-b6de6810dfd6" \
  $B/api/paper/canonical/stock
```

This works **only** when `DEMO_DEVICE_MODE=True` (or `AUTH_DISABLED_LOCAL=True`). With both False the same call returns the shared demo book, not bc207e65 (the header is ignored).

## M1B — login rate-limit / lockout

Brute-force protection on `POST /api/login`, DB-backed (`login_attempt` table, migration `105_login_attempt`).

**Config (settings, safe dev defaults):**

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_LOGIN_MAX_ATTEMPTS` | 5 | Failed attempts (by email OR IP) before lockout. |
| `AUTH_LOGIN_WINDOW_SECONDS` | 900 | Counting window for failures. |
| `AUTH_LOGIN_LOCKOUT_SECONDS` | 900 | Lockout duration measured from the last failure. |

**Expected lockout behavior:** after `MAX` failed logins for an email (or IP) within `WINDOW`, further attempts are rejected for `LOCKOUT` seconds. A successful login clears that email's failure counter; failures also age out of the window automatically.

**Generic error requirement:** a locked-out attempt returns the **same** `401 "invalid email or password"` as a bad password or unknown email — lockout state and account existence are never disclosed.

**Production env values (unchanged from M1/M1A):** `AUTH_DISABLED_LOCAL=False`, `DEMO_DEVICE_MODE=False`, `SESSION_COOKIE_SECURE=True` (behind HTTPS).

**Verification (curl, prod config):**
```sh
# N=AUTH_LOGIN_MAX_ATTEMPTS bad passwords, then one more -> all 401 generic;
# the post-limit attempt is rejected BEFORE password check (locked).
for i in $(seq 1 6); do
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/api/login \
    -H 'Content-Type: application/json' -d '{"email":"a@x.com","password":"wrong"}'
done   # -> 401 x6, identical body
# Correct password while locked -> still 401 (locked). After LOCKOUT expiry
# (or a successful prior reset) -> 200.
```

Note: client IP is taken from `request.client.host`. Behind a reverse proxy, ensure the proxy sets a trusted forwarded-for and the app reads it before public beta (M1B uses the direct peer IP).

## M1C — auth ops (trusted proxy IP + login_attempt pruning)

### Trusted client-IP for rate limiting

The login rate-limiter keys on the client IP. By default it uses the **direct peer IP** (`request.client.host`). Behind a proxy (Caddy/Cloudflare) the direct peer is the proxy, so enable trusted-proxy mode to key on the real client.

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_TRUST_PROXY_HEADERS` | False | When True, honor forwarded client IP **only** if the direct peer is a trusted proxy. |
| `AUTH_TRUSTED_PROXY_CIDRS` | "" | CSV of CIDRs that are trusted proxies (e.g. the Caddy/ingress subnet, or Cloudflare ranges). |

Resolution: if trust is disabled **or** the direct peer is not in `AUTH_TRUSTED_PROXY_CIDRS`, the direct peer IP is used and any `X-Forwarded-For` / `CF-Connecting-IP` is **ignored** (a public client cannot spoof its IP). If the direct peer is a trusted proxy, the resolver prefers `CF-Connecting-IP`, else the **first** `X-Forwarded-For` entry (the original client). Malformed/empty forwarded values fall back to the direct peer.

- **Caddy:** set `AUTH_TRUSTED_PROXY_CIDRS` to the Docker/ingress subnet Caddy connects from; ensure Caddy sets `X-Forwarded-For`.
- **Cloudflare:** put Cloudflare's egress ranges in `AUTH_TRUSTED_PROXY_CIDRS`; `CF-Connecting-IP` is then used as the real client IP.
- Do **not** set `AUTH_TRUST_PROXY_HEADERS=True` without populating `AUTH_TRUSTED_PROXY_CIDRS` — with an empty CIDR list no peer is trusted, so it safely falls back to the direct IP.

### login_attempt pruning

`login_attempt` grows with traffic. Prune periodically:

```sh
make prune-login-attempts          # honors AUTH_LOGIN_ATTEMPT_RETENTION_DAYS (default 7)
```

The prune helper enforces a hard min-keep floor of `WINDOW + LOCKOUT` seconds, so rows needed for active lockout/rate-limit math are **never** deleted even if retention is misconfigured low. No scheduler is added — run it from cron/ops on whatever cadence fits (daily is ample at beta scale).

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_LOGIN_ATTEMPT_RETENTION_DAYS` | 7 | Delete login_attempt rows older than this (floored by window+lockout). |

### Reminder (public env) — unchanged across M1/M1A/M1B/M1C

`AUTH_DISABLED_LOCAL=False`, `DEMO_DEVICE_MODE=False`, `SESSION_COOKIE_SECURE=True` (behind HTTPS).

## Reminder

`X-Auth-User-Id` is a **dev/demo convenience header only**. In production it must never authenticate a user. The only real identity is the `arthos_session` cookie backed by `user_session`. Keep `DEMO_DEVICE_MODE` and `AUTH_DISABLED_LOCAL` False in every public environment.
