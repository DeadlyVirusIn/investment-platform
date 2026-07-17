# Paper guest-ownership threat model

Scope: authorization of the paper-portfolio surface, and the proposed guest
funnel. Branch `security/paper-surface-ownership`. Production frozen; nothing
here is deployed.

## Assets

- Per-user paper books (`user:<uid>:stock`) — holdings, cash, trade history.
- The shared demo/canonical book and engine books — public read, must be
  non-mutable by users.
- User identity (session cookie `arthos_session`, HttpOnly) and — if the guest
  funnel is approved — an opaque guest identity.
- Internal identifiers (`user:<uid>`, DB portfolio uuids, engine book names).

## Trust boundaries

Anonymous browser → API (no server identity in prod today) · session user →
their own book only · owner → admin surface · engine worker → engine books only.

## Threats and current posture (T = closed this sprint, D = design/Option C, ● = pre-existing gap being closed)

| # | Threat | Vector | Posture after this sprint |
|---|--------|--------|---------------------------|
| 1 | IDOR read | `GET /paper/portfolios/{id}` any id | ● gate `paper.py` to ownership/owner |
| 2 | IDOR write | `POST /paper/portfolios/{id}/trade` any id | ● gate to server-derived ownership |
| 3 | Enumeration | `GET /paper/portfolios` lists all | ● owner-only |
| 4 | Raw book-name injection / preclaim | `POST /paper/portfolios` arbitrary name → preclaim `user:<victim>:stock` | ● owner-only create; users never create by raw name (only `resolve_user_stock_portfolio`) |
| 5 | Cross-user read via leak | `risk-dashboard`, `live-nav` emit `user:<uid>` names | ● exclude user books + redact names |
| 6 | Internal id disclosure | raw `portfolio_name`/uuid in responses | ● redaction helper at every emitter |
| 7 | Engine/demo/model mutation | user route targeting an engine/demo/model book | ● writes resolve to caller's own book only; engine excluded |
| 8 | Cross-guest access | guest A reads/writes guest B | D — Option C: opaque per-guest identity, server-derived book, no client targeting |
| 9 | Guest-cookie theft / fixation | steal/replay guest cookie | D — HttpOnly+Secure+SameSite, rotate on claim, short TTL |
| 10 | Claim replay / double-claim race | repeat or concurrent claim of a guest book | D — atomic idempotent claim (unique constraint on guest→owner), second claim no-ops |
| 11 | Double ownership | guest book claimed while user has own book | D — explicit conflict policy (merge / keep-both / choose), never silent overwrite |
| 12 | CSRF on writes | cross-site POST with cookie | verify current CSRF posture (SameSite=Lax on `arthos_session`); writes are POST + JSON; add explicit check if needed |
| 13 | Cache principal leak | react-query key not identity-scoped | canonical/executed keys already auth-scoped (prior sprint); audit remaining keys |
| 14 | Timing/probing oracle | 200 vs 404 reveals foreign book existence | keep bare 404 for foreign/nonexistent (no detail); consistent posture |
| 15 | Stale guest data / unbounded guest creation | abandoned guest books, DoS by mass guest creation | D — bounded guests per client, TTL/retention + reaper, rate limit |
| 16 | Resource exhaustion | mass anon trades | rate limits (`_rate_check` exists for add/follow); extend to any guest path |

## Residual after zero-migration closures (Part 1)

Threats 1–7 closed without a migration and without weakening current prod
behavior (prod already requires login for paper mutation). Threats 8–11, 15 are
inherent to a **new** guest funnel and only arise if Option C is built — they
are the reason Option C needs the migration + owner approval below.
