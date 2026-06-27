# Phase 2 — Retire Operator + Drop `/v2` Prefix (plan)

Status: APPROVED for branch implementation only (no prod deploy).
Branch: `mvp/retire-operator-deprefix` (off `e091453`). Rollback anchor: `e091453` bundle (`index-C5DNbcQE.js`).

## Goal
Retire the legacy Operator surface and make the V2 product the only app, served at root.
Target URLs: `/discover` `/today/pick/:symbol` `/portfolio` `/learn` `/me` `/account` `/admin{,/feedback,/jobs,/system,/observability}`.
Old `/v2/*` URLs must redirect to `/*` (search + hash preserved); `/` lands on the new product.

## 1. Route inventory
- **Operator (root, behind `OperatorGuard` localStorage flag — invisible to beta):** `/overview /action-queue /portfolio /portfolio/intel /events /strategies /signal-lab /decisions /research /alpha-lab /ml-lab /ops /risk /agents`, nested `/options/*` (16), `/diagnostics/pending-t1`, `/legacy/*` (12), `/advanced`.
- **V2 (under `/v2/*`):** discover, portfolios/:slug, start, me, me-legacy, methodology, try/:lessonSlug, reflections, journal, arth, admin(+4 sub), learn(+5), today, today/pick/:symbol, today/options/:observationId, opportunities, catalysts, field-notes, watchlist, portfolio, track-record, account, profile, options, options/portfolio.
- **Conflicts:** `/portfolio`, `/options` (both products) — resolved by removing Operator.
- **Retire (unmount, keep files):** all Operator routes + `/advanced`. **Redirect:** `/v2/*`→`/*`. **Preserve→root:** all V2 routes. **Untouched:** `/api/*`.

## 2. Refactor
- App.tsx: `<Route path="/v2/*" element={<RedirectV2ToRoot/>}/>` (shim first) then `<Route path="/*" element={<V2App/>}/>`. Remove `/`→`/v2` redirect (V2App index handles `/`→discover). Remove OperatorGuard/Shell block + `/advanced` + their imports (files kept).
- `RedirectV2ToRoot`: strip leading `/v2`, `Navigate replace` to remainder + `search` + `hash`.
- Rewrite ~198 hardcoded `/v2/...` → `/...` across ~45 files (quoted forms only; manual review of `lib/onboardingPath.ts`, `lib/arth/contextualLessons.ts`, `data/arthosData.ts`). Update `match()` predicates + `p === '/v2'` active-state in ArthosChrome; AdminNav in Admin.tsx; CommandPalette; Onboarding.
- SW/cache: no change — `main.tsx` already unregisters all SWs + clears caches each load; hashed assets + dynamic index.html auto-bust.
- Deploy (later, on approval): build `web.Dockerfile` → repopulate `compose_web_dist` → Caddy live. No backend/DB.

## 3. Risks
Link rot (mitigate: grep gate), stale SW (already self-clean), old bundle cache (hashed + clear), old `/v2` links (shim), admin protection (backend untouched), onboarding stored paths (audit), reviewer proof (rewrite + verify), beta invite URLs (shim covers — confirm format), VM detached/dirty `V2App.tsx` (reconcile before cutover).

## 4. Test plan
Build green + `grep /v2` clean (only shim). Routes: `/`→discover, `/discover`, `/v2/discover`→`/discover`, `/today/pick/:symbol` (+ `/v2` redirect), `/portfolio`, `/learn`, `/account`, `/profile`, `/start`, `/options`, `/admin`, `/v2/admin`→`/admin`. Admin: owner 5 subroutes, anon blocked, nav owner-only. Product: logged-out reviewer, onboarding "see today's idea", "see why", feedback POST, signup/login/logout, paper portfolio, ReviewerProof/ProofPulse auth states. Compat: old `/v2` invite URLs redirect, search/hash preserved, no SW/cache issue, no console errors. Infra: `/api/health`, workers, tunnel, bot.

## 5. Deployment (no DB/backend)
Branch build → repopulate `compose_web_dist` → auto cache-bust. **Prereq:** reconcile VM detached/dirty prod-local files (`V2App.tsx`, Caddyfile, compose, api) into git before cutover. Rollback: rebuild from `e091453` tree → repopulate volume; keep `index-C5DNbcQE.js` fallback.

## 6. Stop conditions
No prod deploy w/o approval · unmount routes only (no file deletion) · no recommendation logic · no auth/admin backend · no Cloudflare/DNS/firewall · no PackHunters/bot · no DB/migrations · no admin write actions.

## Risk level: MEDIUM. Recommendation: implement + smoke on branch; stage cutover behind beta-invite-URL confirmation + VM reconciliation + low-traffic window.
