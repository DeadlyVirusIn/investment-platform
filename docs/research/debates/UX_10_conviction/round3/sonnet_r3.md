# Model: Sonnet 4.6
## Round: 3

## Final position summary (200 words max)

UX-10 succeeds if and only if the *atom* (the ActionCard) is structurally honest, the *vocabulary* is small enough to mean something, and the *Cockpit* — not the Stream — carries the trust load. Three rounds in, the four-way debate has converged on more than I expected at R1: numeric `0.82` is dead universally; invalidation must precede target; quiet days must be first-class; options needs a different verb namespace. The unresolved disputes are real and structural — verb count, confidence representation, and whether the verb or the thesis is the visual headline.

My final position narrows to: **4 verbs (OPEN/HOLD/TRIM/EXIT), conceding WAIT to Opus's argument that suppression is the right answer**; **named tiers (Provisional/Working/Strong/Conviction) plus freshness timestamp plus event-based expiry — explicitly rejecting both Sonnet R1 countdowns and Opus 2x2 matrix**; **Codex's decision-sentence-as-headline as the card's load-bearing visual**; **bear-case-mandated as a composer-level invariant** (Opus's contribution, the single best idea in the debate); and **Cockpit-as-trust-center with visible decision history including misses**. STRUCTURE for options. Calibration line in the drawer. No countdown clocks anywhere.

## What I maintain from R1/R2

- **Invalidation appears above target on every card** — single most differentiating UI invariant; every fintech competitor does it backwards. Universal convergence by R2.
- **No numeric confidence on primary surfaces** — `0.82` belongs in the drawer or nowhere. Universal lock.
- **Cockpit is the core product, Stream is a launcher** — emergent consensus, uncontested.
- **STRUCTURE as the equity-options separator** — three of four converged.
- **Calibration line in the reasoning drawer** — Cockpit + drawer invariant.
- **Quiet days are first-class** — use Gemini's copy verbatim.
- **Trust safeguards as engineering invariants, not designer convention** — Codex's "refuses to render" governance model.
- **Decision sentence is the largest element on the card** — conceded to Codex in R2; maintained.
- **Driver / Counter / Catalyst thesis triplet** — held since R1; merged with Opus's bear-case rule.

## What I conceded across R2-R3

- **Three verbs → four verbs.** Opus is right that `TRIM` is a distinct user mental model from `EXIT`, not a scale modifier on `CLOSE`. My R1 hack ("`TRIM`/`ADD` as scale modifiers") under-weighted the most common long-horizon action. Final set: **OPEN · HOLD · TRIM · EXIT**.
- **Drop `WAIT` as a verb.** My R1 said suppress; my R2 added `WAIT` back via Opus's 5-verb set. I now re-concede to my own R1: if the engine has no action, ship no card. Codex's "user owns NVDA, recommendation changes from ACCUMULATE to WAIT" counter-example is real but is solved by re-issuing the existing thesis card with a new `HOLD` verb and a "do not chase" line — not by inventing a `WAIT` card.
- **Visible countdown clocks die.** Opus's critique that "4 of 6 days remaining" is a casino mechanic and reintroduces fake-precise time is correct. Replace with **freshness timestamp + event-based expiry** (Codex's "Valid until earnings or close below $182"). The auto-demotion behavior survives as a backend invariant.
- **Decision Diet threshold lowered from 8 to 4 cards/24h.** Opus's R2 critique that 8 is "already in a hyperactive state" lands. But: I concede further to Codex's R2 — make it a *nudge* (logged, surfaced as a Cockpit reflection), not an interstitial that blocks research. Friction-as-reflection beats friction-as-blocker.
- **Hero cap tightened from 5 to 3.** Opus + Codex both at 3; my R1's 5 was too generous.
- **Bear-case-mandated rule adopted verbatim** as a composer-level invariant (Opus's contribution).
- **"Compared candidates" tab in the drawer adopted** (Opus's contribution).

## Open disputes I want documented in the master

1. **Verb count: 4 (Sonnet+Opus) vs 7 (Codex+Gemini).** Fundamental, not framing. Codex/Gemini believe the verb carries semantic load the sentence cannot; Opus and I believe the sentence carries it. **Synthesis recommendation: lock 4 verbs (OPEN/HOLD/TRIM/EXIT)** with Codex's 7-grouped-into-4-families documented as the dissent. Codex's strongest argument — beginners benefit from `WATCH` as "thesis forming" — is better solved by the lifecycle pill (locked UX-8), not the verb namespace.

2. **Confidence representation: named tiers + freshness (Sonnet) vs 2x2 matrix (Opus) vs bands + sub-scores (Codex) vs F/T/M ring (Gemini).** **Synthesis recommendation: named tiers (Provisional/Working/Strong/Conviction) + dot glyph (●●●○) + freshness timestamp + event-based expiry.** Absorbs Opus's matrix as the *glyph* and Codex's expiry language. Rejects Gemini's F/T/M bar as engineering vocabulary (Opus correctly attacked this in R2).

3. **Verb-as-headline (Sonnet/Codex) vs thesis-as-headline (Opus).** Deepest unresolved structural question. **Synthesis recommendation: decision sentence as headline, verb as small label, thesis name as subhead.** Opus's pure thesis-first inversion (verb as bottom-right pill) makes the product feel evasive — Codex's R2 critique lands. ActionCard is a decision unit; Cockpit is a thesis unit.

4. **Color saturation ceiling.** I propose ≤50% (tightened from R2). Gemini ships Material Indigo `#3F51B5` (~70% saturation). **Synthesis recommendation: lock at ≤50% for any conviction-bearing color.** Reject Gemini's Indigo as Material 2014 cosplay.

5. **Cockpit beginner-gate: 24h consideration window (Sonnet) vs Plan-a-trade button (Opus).** **Synthesis recommendation: 24h window for beginners; Plan-a-trade button for intermediate+ tiers.** Friction-as-time survives PMs better than friction-as-click.

6. **Decision Diet style: Sonnet's interstitial vs Codex's anti-paternalism.** I concede Codex's middle path: **log + surface in Cockpit reflection, do not block research.** The harder interstitial is reserved for real-money phase.

## Final answers per question

### Q1. Conviction language

**Lock 4 verbs: OPEN · HOLD · TRIM · EXIT.** Drop BUY/SELL (order-ticket vocabulary on a read-only surface = bait-and-switch). Drop ACCUMULATE/REDUCE (sell-side euphemisms; sentence carries the nuance). Drop WATCH (no-opinion verbs are signal spam). Drop WAIT (non-action verbs ship no card). Verbs render as 11px uppercase tracked monochrome labels — single neutral color (`#9CA3AF`). The verb is a *label* on the card's state; the *decision sentence* is the headline. Codex's and Gemini's 7-verb / 5-verb defenses are documented as dissents; the master should pick 4.

### Q2. Confidence system

**Four named tiers + dot glyph + freshness timestamp + event-based expiry.** `Provisional / Working / Strong / Conviction` with `●○○○` through `●●●●` glyphs. Every card carries a `Last reviewed: 14h ago` timestamp and `Valid until earnings May 21 or close below $182` (Codex's framing). Auto-demotion when the freshness window elapses, logged in the decision history. **No countdown clocks visible anywhere** — Opus's casino-mechanic critique landed. **No 0.82 anywhere on the card.** No stars (Yelp), no rings with progress fills (fitness-app), no F/T/M segmented bar as primary (engineering vocabulary). Numeric backing scores live in the drawer for power users only.

### Q3. ActionCard density

**Card schema (refuses to render if any field missing):** `{verb, ticker, decisionSentence, confidenceTier, freshnessTimestamp, expiryCondition, invalidation, thesis: {driver, counter, catalyst}, target, horizon, bearCaseGlyph, snoozeAffordance}`. Visual hierarchy top-to-bottom: lifecycle pill + tier glyph + freshness; ticker + thesis name; **decision sentence as the largest element** (Codex, ~120 chars, 18px); driver/counter/catalyst triplet; **invalidation BEFORE target** (Sonnet, locked); horizon. Bear-case glyph next to verb pill opens the bear case directly. Width 720px stream / 480px compact. Background `#0F1115`, single 1px border at `#1F2329`, no gradients on the card itself.

### Q4. Overview hero

**Replace "AI FOUND 3 HIGH-CONFIDENCE MOVES TODAY" with structural hero.** Three sections: regime ribbon (one line), `Your active positions` (existing holdings outrank new ideas), `What the engine believes more strongly` (promotions since last visit). **Cap at 3 thesis cards.** Quiet-day state uses Gemini's copy verbatim: *"Market regime: noisy. Maintaining existing positions. No new entries recommended."* No "found," no "moves," no "today's picks," no all-caps urgency. The hero ends — no infinite scroll.

### Q5. Stock detail (Research Cockpit)

**This is the core product.** First-paint hierarchy: header band (ticker, neutral price), conviction strip (verb · tier · freshness · invalidation distance), **two-column thesis (Driver | Counter, equal visual weight)** with catalyst below, price ladder (vertical, not chart), then below the fold: chart with invalidation drawn as horizontal line, financials (only thesis-relevant metrics), news + filings (thesis-filtered, with "Counter-evidence first" toggle from Opus), reasoning drawer, and **decision log per ticker including misses** (the highest-leverage trust-builder no fintech currently does). For beginners, levels collapse behind the **24h consideration window**, not a button.

### Q6. Options experience

**STRUCTURE as the only top-level options verb**, with strategy type as sub-label (`STRUCTURE · Defined-risk bullish · NVDA`). Hard rules: defined-risk only by default; max loss named first; POP visible next to reward/risk; no naked options outside an explicit advanced toggle; no 0DTE on the hero; risk graph always visible; no "Buy now" CTA — only "[See plan]"; every options card linked to an underlying equity thesis (Codex). Three-screen primer interrupts the first options card per user. Risk dot is the *only* color-coded element in the system, only ever amber or red.

### Q7. Trust safeguards

**13 engineering invariants, code-enforced, schema-rejected if violated:**
1. Max 3 thesis cards in hero
2. Max 2 `Conviction` cards per user per week (server-enforced; Opus's per-ticker refinement merged)
3. No card without invalidation
4. No card without horizon
5. **Bear-case-mandated for `Conviction` tier** (Opus, locked)
6. Decision Diet: > 4 cards/24h surfaces a Cockpit reflection (not a blocker; Codex's anti-paternalism conceded)
7. Confidence half-life enforced via auto-demotion (no visible countdown; backend only)
8. No saturation > 50% on any color
9. No motion > 240ms or > 8px translation
10. Weekly Calibration card showing tier hit rates
11. **WAIT-equal-to-ACT** visual treatment (Opus; reframed as visual dignity for HOLD, not literal CTA buttons per Codex's R2 caveat)
12. **Snooze affordance per thesis** (Opus, adopted)
13. **Action ledger per ticker including misses** (Opus, adopted)

### Q8. Visual system

**Survives:** dot glyphs (●●●○), verb labels (monochrome only), single-layer cards, 8px grid, three depth levels (`#0B0D10`, `#0F1115`, `#13161B`), four-size typography lock (24/16/14/11). **Dies:** confidence rings (fitness-app vocabulary; Codex's critique landed), conviction bars (read as battery-low), gradients, conviction tints as background fills (mood-ring failure mode), score glyphs (decoration on a number), all neon. **Conviction tint:** `#7B8CFF` at 8% opacity as a 1px left border for `Strong+` only — never as fill. **Risk red:** `#C24A4A` (desaturated). **Premium = restraint.** Bloomberg is industrial; Linear, Stripe, and Apple are premium. Reject Gemini's Indigo `#3F51B5` as Material 2014 cosplay.

### Q9. AI reasoning drawer

**Single scroll surface** (not tabs — tabs hide the bear case behind a click): plain-language thesis recap (60 words) → **3 drivers / 3 counters with sub-confidence per claim** → what changed since last review → **calibration line** (`Current Strong tier hit rate: 60% (rolling 90d). Below 70% target.`) → **compared candidates** (Opus: "AI considered AMD, TSM, MU; picked NVDA because…") → **my pattern with this AI** (Opus: user-specific reflection) → engine version + last retrain date (tiny grey footer). **Hidden by default:** factor weights, model class, SHAP values, raw chain-of-thought, prompt scaffolding. **Never shown:** marketing language, "Powered by AI" claims, raw probabilities to 4 decimal places.

### Q10. Biggest failure modes

**Top 3, ranked by likelihood:**
1. **Verb gravity** — within 2 sprints, PMs ship `NIBBLE`, `RIDE`, `EXIT 50%` because the namespace expanded surface area. *Mitigation: ship 4, resist expansion 6 months, schema-reject unknown verbs.*
2. **Confidence inflation** — engine learns `Conviction` cards drive engagement, thresholds drift, system collapses to binary. *Mitigation: hard rate-limit at the renderer, public tier-distribution dashboard, alert if `Conviction` exceeds 4% of cards in a month.*
3. **Trust collapse from one bad call** (Opus's contribution) — first time the AI is confidently wrong on AAPL/NVDA/TSLA, the entire framing dies. *Mitigation: bear-case-mandated rule + visible track record per ticker + decision log including misses.*

**Honorable mentions:** Cockpit cosplay (beginners feel qualified to act on stocks they shouldn't hold; mitigated by 24h consideration window), thesis theater (Codex's R2 contribution: lots of smart prose, weak decision help), generic stock-picker drift (mitigated by safeguards-as-invariants).

### Q11. Final synthesis

**Lock 5 things in the master, in priority order:**
1. **4-verb system + 4-tier confidence + decision-sentence-as-headline + invalidation-above-target.** Card atom is structurally honest. Phase 10A.
2. **Bear-case-mandated rule as composer-level invariant.** Single biggest differentiator. Phase 10A.
3. **Research Cockpit with visible decision history + calibration line.** Trust center; Cockpit > Stream. Phase 10B.
4. **Trust safeguards as 13 engineering invariants** (schema-enforced, with tests). Phase 10C, parallel.
5. **STRUCTURE for options with loss-named-first.** Phase 10D.

**Deprioritized:** visual system polish (gradients, glyphs, motion). Phase 10G+. If the verbs/tiers/contract/cockpit/safeguards are right, the visual system falls out naturally; if wrong, no polish saves us.

## Master doc recommendations

1. **Lock 4 verbs (OPEN/HOLD/TRIM/EXIT)** and document Codex's 7-grouped-into-4-families as dissent. M1, Public, Composer all suffered verb sprawl; the empirical pattern favors locking small.

2. **Lock confidence as `4 tiers + dot glyph + freshness timestamp + event-based expiry`** — Sonnet tier names + Opus glyph + Codex expiry conditions. Reject Gemini's F/T/M ring as primary; relegate to drawer evidence breakdown.

3. **Lock the bear-case-mandated rule as a composer-level engineering invariant** (Opus's contribution). Structural — enforced where the recommendation is generated, survives PM rotations. A `Conviction` card cannot ship without an articulated, credible counter; composer fails the build if the bear case is missing or stub.

4. **Lock the ActionCard schema as a refusing-to-render contract:** `{verb, ticker, decisionSentence, confidenceTier, freshnessTimestamp, expiryCondition, invalidation, thesis: {driver, counter, catalyst}, target, horizon, bearCaseGlyph, snoozeAffordance}`. Codex's R1 governance model; my list is the superset.

5. **Lock the quiet-day hero state with Gemini's copy verbatim:** *"Market regime: noisy. Maintaining existing positions. No new entries recommended."* Triple convergence in R1; the most trust-building copy in the product.

If the master can lock only one: **the bear-case-mandated composer invariant.** One confidently-wrong call on a high-profile ticker destroys the entire framing; the bear case shown before the user acted converts the loss into normal variance. Everything else is downstream.
