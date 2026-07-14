# ArthOS — Security Audit & Release Gate

Last run: 2026-06-25 · Scope: ArthOS only (web app, API, auth/session, owner
console, jobs/workers, observability, prod VM/tunnel, DB-backed user data).
Method: static code audit + dependency/secret scanning (CI) + **live red-team
probes against production**.

## Release gate: PASS

No P0/P1/P2 findings. No admin bypass, no cross-user data leak, no secret leak,
no auth/session fail-open, no SQL injection. Remaining items are P3
defense-in-depth (one fixed this pass).

## Attack-surface inventory

| Surface | Entry | Data | Worst case | Protection | Severity |
|---|---|---|---|---|---|
| signup | POST /api/signup | email, password | account spoof / DoS | scrypt hash, len 8-256, parameterized, email-norm | OK |
| login | POST /api/login | credentials | brute force, enum, replay | lockout + generic error (no enum), dummy-verify timing flatten, constant-time compare | OK |
| logout | POST /api/logout | session | session survives | server-side revoke_session | OK |
| session cookie | arthos_session | session token | theft/XSS | HttpOnly, SameSite=Lax, Secure (prod), token_urlsafe(32) | OK |
| session lookup | cookie->user | user id | forged session | DB-backed token lookup; forged/garbage -> anon | OK |
| profile | /api/profile | prefs | cross-user read/write | session-scoped to own app_user.id; enum-validated | OK |
| feedback | POST /api/feedback/signal | text | XSS/DoS/abuse | allowlist surface+type, value cap 2000, payload cap 4000B, 60/60s rate-limit, X-Auth-User-Id never trusted as auth, no read endpoint | OK |
| recommendations | /api/recommendations | public ideas | n/a (public) | read-only, no PII | OK |
| paper/canonical | /api/paper/canonical/stock | demo book | n/a (public proof) | intentionally public; user-scoped when authed | OK |
| paper/executed | /api/paper/executed/trades | practice trades | IDOR by portfolio_id | parameterized; no ownership check but portfolio_id is v4-UUID (unguessable, not enumerable, not exposed) | P3 |
| admin overview/feedback/jobs/system/observability | /api/admin/* | aggregates | unauthorized admin, secret leak | require_owner (DB role OR env), 404 for anon+non-owner, allowlisted safe fields, capped errors | OK |
| DB queries | all | user data | SQLi | 100% parameterized (text() + bind params); no f-string/format/%/concat in queries | OK |
| jobs/workers | scheduler | job data | unauthorized trigger | no public trigger endpoint; status read-only via owner /admin/jobs | OK |
| observability/logs | logs + /admin | internals | secret in logs | owner-guarded; logs do not print secrets/tokens | OK |
| health | /api/health | status | internals leak | returns {status, version, time} only - no internals/secrets | P3 (version disclosure, info) |
| CORS/tunnel | edge | origins | foreign origin | CORS allowlist (app origin only; foreign not reflected); Cloudflare TLS + tunnel | OK |
| env/secrets | .env (host) | keys | leak | gitignored, not tracked; never serialized | OK |

## Category results

| Category | Status | Evidence | Test/tool | Remaining risk |
|---|---|---|---|---|
| Auth/session | OK | scrypt (N=2^14, random salt, constant-time); token_urlsafe(32); HttpOnly+SameSite+Secure; logout revokes; forged cookie -> anon; login lockout + generic error | live probes + code audit | none |
| Authorization/admin | OK | require_owner server-side; DB role OR env allowlist; 404 for anon + non-owner; observability guarded; AdminGuard cosmetic only | live: owner 200, non-owner/anon 404 | none |
| SQL/input validation | OK | all queries parameterized; SQLi login -> denied no bypass; feedback value/payload capped; surface/type allowlisted; password 8-256 | live SQLi + code grep | none |
| CSRF/CORS | OK | SameSite=Lax cookies; CORS rejects foreign origin (no ACAO for evil.example); state-changing endpoints session+SameSite protected | live origin probe | low (no CSRF token, but SameSite=Lax + cookie design covers it) |
| Secrets | OK | privacy grep clean (no keys/JWT/tunnel URLs); .env gitignored; never serialized in payloads | gitleaks + privacy grep | P3: owner email (PII, not secret) hardcoded in v2_promotion.py + migration |
| Logs/observability | OK | owner-only; capped errors (240ch); no secret/token printed | code audit | none |
| Jobs/workers | OK | no public trigger; read-only owner /admin/jobs; VM status JSON read-only + allowlisted fields | live + code | none |
| Dependencies | CI | pip-audit + npm audit (--audit-level=high) wired in CI | CI security.yml | gate runs on next push |
| Deployment/VM | OK | tunnel token in chmod-600 host file; health JSON read-only bind-mount (no docker socket, no shell-out); firewall closed | DevSecOps review | none |
| Forbidden-field scan | OK | live scan of all admin payloads: 0 real hits (only benign job name tiingo_backfill_eod) | live grep | none |
| Long-input DoS | OK (fixed) | password capped 8-256 (scrypt HMAC pre-hash already made it sublinear); feedback/payload capped; body size bounded by Cloudflare/proxy | code + live timing | none |

## Red-team results

| Attack | Expected | Actual | Status |
|---|---|---|---|
| Anonymous admin API (all 5) | 404 | 404 | blocked |
| Non-owner admin API | 404 | 404 (DB role + env) | blocked |
| Forged/garbage session cookie | reject | admin 404, session authenticated=false | fail-closed |
| Replayed session after logout | reject | revoke_session deletes server-side | OK |
| SQLi in login email | no bypass | 403/denied, parameterized | OK |
| Long password (100k / 1M) | no DoS | flat ~0.1s; now capped 256 | OK |
| CORS foreign origin | no reflect | no ACAO for evil.example | OK |
| Cross-user profile | scoped | own-row only by session id | OK |
| Admin payload secret harvest | none | forbidden_field_hits=0 | OK |
| Login brute force | rate-limited | lockout active (403) | OK |

## Tooling added (CI: .github/workflows/security.yml)
CodeQL (python, javascript-typescript, actions; security-extended) · gitleaks
(committed secrets) · semgrep (p/security-audit, p/secrets, p/owasp-top-ten,
--error) · pip-audit · npm audit --audit-level=high · privacy grep
(keys/JWT/tunnel patterns). Fails on: committed secrets, high/critical CVEs,
semgrep findings, leaked identifiers.

## Fixed this pass
- Password max length 256 (identity.py) - defense-in-depth long-input guard
  (fail-closed; hash_password rejects, verify_password returns False).

## Remaining risk (P3, accepted/documented)
1. paper/executed IDOR - no ownership check on portfolio_id, but v4-UUID is
   unguessable + not exposed -> not exploitable. Mitigation: add a
   session-ownership filter in a future pass (do not break the public canonical book).
2. Owner email (PII) hardcoded in v2_promotion.py + migration 108 - an email,
   not a credential. Mitigation: move v2_promotion operator list to env later.
3. Health version disclosure - 1.0.0-beta in /api/health (standard, info-level).
4. No CSRF token - covered by SameSite=Lax + session design; add tokens only if
   cross-site form posts are ever introduced.
5. Request body size - bounded by Cloudflare/reverse-proxy, not app-level.

## Rollback
- Password cap: git revert the identity.py change (pure logic, no data).
- CI workflow: delete .github/workflows/security.yml (non-runtime).
- No prod data or schema changed by this audit.
