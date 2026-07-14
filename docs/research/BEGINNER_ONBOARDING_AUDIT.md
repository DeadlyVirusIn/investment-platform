# Beginner Onboarding Audit (2026-06-18)

First-time-user journey, captured on a fresh device (no prior state).
Screenshots this session: `apps/web/__j1_landing.png … __j8_options.png`.
**Audit only — nothing implemented.**

Target funnel (user's framing):
**Discover → Learn → Practice → Build → Automate → Invest**

---

## 1. Journey map (current state)

| # | Step | Route | What the beginner sees | "What next?" answered? |
|---|------|-------|------------------------|------------------------|
| 1 | Landing / onboarding | `/v2` → Welcome | Strong value prop ("Your AI Investing Copilot… literacy by Day 90, nothing real at stake"). Single "Begin Day 1" CTA **below the fold** on mobile. | Partial — CTA needs a scroll |
| 2 | Day 1 "Start here" | `/v2/start` | **Excellent** structured plan: READ 6m → SEE 8m → WRITE → WATCH, "~27 min, nothing graded, progress saved". | Yes (best screen in the app) |
| 3 | Discover | `/v2/discover` | Tabs (Stock Ideas / Options Practice), Model Portfolios, themes, social proof. Clear taxonomy. | Yes |
| 4 | Idea detail | `/v2/today/pick/:sym` | "Royalty Pharma (RPRX) — Buy", sector + confidence + explainer, **WHAT TO DO NEXT**, Entry/Target/Exit, Add to paper, "Paper means practice money". | Yes (strong) |
| 5 | Add to Paper → Paper Book | `/v2/portfolio` | After adding, the book shows **"Practice account is unavailable right now"** + "No priced holdings". | **No — looks broken** |
| 6 | Paper Book (revisit) | `/v2/portfolio` | Same unavailable state. Good intro copy, but no positive confirmation. | No |
| 7 | Model Portfolio | `/v2/portfolios/:slug` | Theme, +8047.5% total return, −63.2% max DD, honest survivorship disclosure, holdings w/ names. | Partial — no "follow / add" next step in view |
| 8 | Options Practice | `/v2/discover` (tab) | Warning + "advanced practice setups" explainer; enriched cards. | Yes |

Funnel coverage:
- **Discover** ✅ strong. **Learn** ✅ exists (`/v2/start`, `/v2/learn`) but buried after first run. **Practice** ⚠️ broken-feeling (step 5). **Build** ⚠️ portfolios exist but no bridge from single ideas. **Automate** ❌ absent. **Invest** ❌ absent (paper-only MVP, by design).

---

## 2. Drop-off risks (ranked)

1. **P0 — Paper Book "unavailable" after the first add.** The add *works*
   (`/api/paper/canonical/stock` → `open_positions_count: 1`) but returns
   `status: "no_live_snapshot"` (nav/cash null) until the next snapshot cycle,
   so the UI says "Practice account is unavailable right now." A beginner who
   just took their first action sees apparent failure → highest-leverage
   drop-off. Fix = success confirmation + "values update at the next market
   snapshot" empty state (not "unavailable").
2. **P1 — Landing CTA below the fold.** First action requires a scroll on
   mobile; some users bounce before finding "Begin".
3. **P1 — Day-1 flow is buried.** The best guidance screen (`/v2/start`) is
   only reached by clicking "Begin" once; no persistent "Resume Day 1 / Continue
   your path" entry after first run.
4. **P1 — No bridge single idea → portfolio.** After following one idea, nothing
   says "ready for a diversified set? try a model portfolio." Step 7 has no
   "Follow this portfolio (adds to paper)" CTA in view.
5. **P2 — Model-portfolio +8047% headline** can read as a promise despite the
   honest disclosure; survivorship caveat is below the number.
6. **P2 — "When am I ready for options?"** never answered — only a blanket
   warning. No readiness signal (e.g. "after N practice trades").

---

## 3. Missing guidance — the five beginner questions

| Question | Answered today? | Where it's missing |
|---|---|---|
| What do I do next? | Mostly | Paper Book (step 5/6), Model Portfolio (step 7) |
| Why am I here? | Yes | — |
| What is paper trading? | Yes | (PickPage explainer + Paper Book intro) |
| When should I move to portfolios? | **No** | No prompt after 1–N single ideas |
| When should I look at options? | **No** | Only a warning; no readiness cue |

Cross-cutting gap: **no persistent progress spine.** Day-1 sets up "one idea →
one decision → one note → watch it", but after onboarding the app doesn't carry
that thread (no "Day N / next step" affordance on the main surfaces).

---

## 4. Recommended onboarding flow (Discover → Learn → Practice → Build → Automate → Invest)

A single, always-visible **"Your path"** spine that advances by *doing*, not reading:

1. **Discover** — land on one idea (today's top). Already strong. Add a one-line
   "New here? Start your 5-minute path →" pointing to `/v2/start`.
2. **Learn** — the Day-1 READ (what you own when you buy a stock). Keep it, but
   make it resumable from a persistent "Continue your path" card on Discover.
3. **Practice** — Add the idea to paper. **Fix the confirmation** (P0): after
   add, show "✓ Added to your practice book — RPRX, $1,000. Values update at the
   next market snapshot." with a "See your book →" CTA.
4. **Build** — after the 2nd–3rd single idea, surface "Want a ready-made mix?
   Follow a model portfolio" with a one-tap **Follow (adds to paper)** on the
   model-portfolio page.
5. **Automate** — (future) recurring/auto-follow a portfolio; "let ArthOS keep
   this in sync." Not built — roadmap item.
6. **Invest** — (future, out of MVP) real-money handoff. Keep paper-only for now;
   add an explicit "this is practice; real investing comes later" signpost so the
   ceiling is intentional, not a dead end.

Readiness gates (answer the two unanswered questions):
- **→ Portfolios** after ≥2 single-idea adds: "You've practiced individual ideas
  — diversify with a model portfolio."
- **→ Options** after ≥5 stock practice trades (or an explicit "I know options"
  toggle): unlock Options Practice prominence; until then keep it behind the
  current warning.

---

## 5. Prioritized roadmap

**P0 (do first — fixes apparent breakage)**
- Paper Book: replace "unavailable" with a positive empty/success state when
  `status=no_live_snapshot` but positions exist ("Position added; values pending
  next snapshot"). Add post-add confirmation toast on PickPage.

**P1 (activation)**
- Persistent "Your path / Continue Day 1" card on Discover (resumable `/v2/start`).
- Move/condense landing so "Begin" is above the fold on mobile.
- Single idea → portfolio bridge: "Follow (adds to paper)" CTA on model-portfolio
  page + a nudge after 2–3 adds.

**P2 (depth + readiness)**
- Options readiness gate (N practice trades) + "you're ready for options when…".
- Reframe model-portfolio headline so the survivorship caveat sits with the number.
- "Automate" concept (recurring follow) — design spike.
- "Invest" signpost clarifying the intentional paper-only ceiling.

---

## 6. Screenshots
Captured this session (mobile 430px, fresh device) at
`apps/web/__j1_landing.png` … `__j8_options.png`. Step-by-step innerText is
quoted inline above. (Not committed — binaries; re-capture via the journey
script if needed.)
