# Model: Sonnet 4.6
## Round: 1

## Position summary (300 words max)

UX-10 will fail if it ships seven verbs. The pivot from "observational" to "conviction" is correct, but the proposed verb set (BUY/ACCUMULATE/WATCH/HOLD/REDUCE/SELL/WAIT) is a category error: it borrows sell-side equity-research vocabulary from 1995 and welds it onto a paper-trading copilot. That is the "stock-picking casino" failure the brief warns against, in business casual.

Collapse to **three verbs** — `OPEN`, `HOLD`, `CLOSE` — and let the *Brief* (locked in UX-6) carry conviction *as a thesis*, not a commandment. The hero must never say "AI FOUND 3 HIGH-CONFIDENCE MOVES TODAY" — a Robinhood push notification with extra steps. Replace it with a structural hero: "What changed in your book" + "What the engine believes more strongly."

Confidence must be **a tier with a half-life**, never a number. `0.82` is fake-precise theatre; users round it to "82% chance of going up," which is wrong on its face. Four tiers — `Provisional / Working / Strong / Conviction` — each with an explicit decay clock so confidence cannot exist outside of time.

The Research Cockpit becomes the core product; the Stream becomes a launcher. ActionCards must show invalidation *above* entry/target — a card that surfaces what would kill the thesis before what would print money is structurally honest; the reverse is a pitch deck.

Options use a different verb namespace entirely (`STRUCTURE`, not `BUY CALL`) to break the slot-machine pattern users have built up from Robinhood and WSB. If we ship `BUY CALL TSLA` on a card, we have already lost.

## Q1. Conviction language

**Drop the seven verbs. Use three: `OPEN`, `HOLD`, `CLOSE`.** Optional `TRIM`/`ADD` as scale modifiers, never primary verbs.

Drop BUY/SELL: they are *order types*. Brief says read-only research. Showing BUY on a card you cannot click "Buy" on is bait-and-switch — the user's hand is already moving toward a button that doesn't exist. Largest source of casino-feel in any "AI picks" product I've audited (M1, Public, Composer, Atom).

Drop ACCUMULATE / REDUCE: sell-side euphemisms. Goldman cosplay. We have OPEN/CLOSE/TRIM/ADD.

Drop WATCH: WATCH is what you do when you have no opinion. If the engine has no opinion, the card shouldn't exist. WATCH is how stock-picking apps pad daily output. #1 source of signal spam.

Drop WAIT: a non-action dressed up as guidance. If the recommendation is wait, send no card.

**Visual treatment:** verbs are 11px uppercase tracked (`letter-spacing: 0.08em`) labels in a single neutral color (`#9CA3AF` dark, `#4B5563` light). **No verb-color coding.** OPEN-green, CLOSE-red is the casino tell. The verb is a *label*, not a *signal*. Conviction lives in tiers (Q2) and thesis (Q5), not chrome.

**Defending the weakest claim:** "But users want to know whether to buy or sell!" — `OPEN` paired with a directional thesis ("OPEN long NVDA, $172, target $215, invalidation $158") tells them exactly that without LARP-ing as a brokerage. Other models will say I'm being precious. I am. Precision in vocabulary is how you avoid casino drift.

## Q2. Confidence system

**Numeric `0.82` is unforgivable. Stars are infantilizing. High/Med/Low is lazy. Tiers + decay is correct.**

Proposed system: **four named tiers, each with a visible decay clock.**

| Tier | Internal score range | Visual | Decay window |
|------|---------------------|--------|--------------|
| `Provisional` | 0.40–0.55 | Hollow ring, 1 segment filled | 24h |
| `Working` | 0.55–0.70 | Ring 50% filled | 72h |
| `Strong` | 0.70–0.85 | Ring 75% filled | 6d |
| `Conviction` | 0.85+ | Ring fully filled, single tick mark | 14d |

Below 0.40, no card. We never ship a "Provisional minus" or "Low" tier — that's signal spam dressed up as humility.

**The decay clock is the load-bearing element.** Every card shows: `Strong · 4 of 6 days remaining`. Confidence becomes a *time-bounded claim*, not vibes. When time runs out, the card auto-demotes and re-evaluates. Kills the "confidence with no decay" anti-pattern in the brief.

**Why not numeric?** A user seeing `0.82` performs three wrong inferences: (1) rounds it to "82% probability of going up," (2) assumes two decimals of resolution exists, (3) shops for the highest number on the page — exactly the action bias UX-10 is supposed to prevent. Numeric scores belong in the reasoning drawer (Q9), never on the card.

**Why not stars?** Stars are how Yelp rates burritos. 5-point resolution invites "is 4 stars enough?" anxiety.

**Why not High/Med/Low?** Three buckets is too few — Medium becomes 70% of cards, system collapses to binary High/not-High. Four named tiers force the engine to commit.

**Defending the weakest claim:** "Won't `Conviction` feel overconfident?" Only if we let it fire often. Contract: at most **2 `Conviction` cards per user per week**, rate-limited server-side. Excess gets demoted. Scarcity is what makes the tier mean something.

## Q3. ActionCard density

**Card spec, in scan order top-to-bottom:**

```
[Lifecycle pill]  [Conviction tier ring]            [Decay clock]
┌─────────────────────────────────────────────────────────┐
│  NVDA · NVIDIA                                          │  ← 18px, semibold
│  Open long  ·  $172.40 entry zone                       │  ← 14px verb+entry, single line
│                                                         │
│  THESIS                                                 │  ← 11px uppercase, tracked
│  Margin expansion in data-center segment is             │  ← 14px, max 240 chars, 3 lines
│  re-accelerating ahead of consensus; capex digestion    │
│  fears now contradicted by Q1 hyperscaler guidance.     │
│                                                         │
│  INVALIDATION                                           │  ← 11px uppercase, tracked
│  Close below $158 on > 1.4× ADV, or hyperscaler         │  ← 14px, max 160 chars, 2 lines
│  capex revision below +18% YoY.                         │
│                                                         │
│  Target zone $208–$222   ·   Hold horizon ~6 weeks      │  ← 13px, secondary text
└─────────────────────────────────────────────────────────┘
[See the working] →                              [Pin] [Mute]
```

**Width:** 720px in stream view, 480px in compact list. **Vertical rhythm:** 8px grid, 24px section gaps. **Background:** `#0F1115` on dark theme, no gradient, no border glow. **One subtle 1px border at `#1F2329`** — that is the entire card chrome.

**Critically: invalidation appears above target.** Non-negotiable. Most fintech UI surfaces upside before downside; this trains users that the engine is a hype machine. Putting "what would kill the thesis" above "what would make money" is the structural-honesty signal that sets us apart from M1 / Public / Composer.

**Hidden:** confidence number, factor weights, model version, backtest stats, sizing, brokerage hand-offs. All in the drawer.

**Missing from the original proposal:** *horizon*. A card with no time horizon is a tweet. "~6 weeks" distinguishes long-horizon investing from day-trading.

**Defending the weakest claim:** "240 chars of thesis is too much." Users will read it *because we cut everything else*. The card isn't competing with TikTok — it's competing with their other NVDA browser tabs. If our thesis is shorter than a Stocktwits post, why would they trust it?

## Q4. Overview hero

**"AI FOUND 3 HIGH-CONFIDENCE MOVES TODAY" must die.** It fails on six counts:

1. "AI FOUND" is anti-AI-theatre — directly violates the locked ban from UX-9.
2. "HIGH-CONFIDENCE" is overconfident absolute language — anti-pattern.
3. "MOVES" is gambling vocab.
4. "TODAY" creates daily action pressure → overtrading.
5. The all-caps shouting is casino aesthetic.
6. The implicit promise ("we found them, you act") inverts the copilot relationship — the user is supposed to make decisions; we surface evidence.

**Replacement hero — two stacked sections, no exclamation:**

```
Today                                     Tue · May 9
─────────────────────────────────────────────────

What changed in your book
3 holdings crossed an attention threshold.
[Card] [Card] [Card]

What the engine believes more strongly
2 theses promoted to Strong since Friday.
[Card] [Card]
```

Hero divided by *structural relevance to the user*, not engine enthusiasm. "Your book" first, "engine theses" second — existing positions are always more important than new picks.

**Scarcity rule:** hero shows at most 5 cards total. Surplus goes to `/Ideas`. **No infinite scroll** in the hero. The hero ends.

**Quiet day rule:** if nothing crossed thresholds: `Quiet day. Two holdings on watch, no decisions required.` Not "0 high-confidence moves." Quiet days exist; the product must respect them. Single biggest differentiator from a "hot picks" app.

**Defending the weakest claim:** "Won't users churn on quiet days?" Some will. They are not our users. Anyone needing a daily dopamine hit from a financial app should use Robinhood. Our retention model is *trust accumulation over years*, not DAU.

## Q5. Stock detail (Research Cockpit)

**This is the core product. The Stream is a launcher; the Cockpit is where decisions get made.**

First-paint hierarchy (above fold, 1080px viewport):

1. **Header band (96px):** `NVDA · NVIDIA`, price + day change in *neutral grey* (no green/red until held >5s), market cap, float, sector chip.
2. **Conviction strip (64px):** `Engine view: Open long · Strong · 4d remaining` + decay clock + invalidation distance. One glance: what we think, how confident.
3. **Thesis block (240px):** structured triplet — `Driver`, `Counter`, `Catalyst`. Three short paragraphs, ~80 words each. Longest text on the page; earns its place.
4. **Price ladder (320px):** vertical, not a chart. Current price marker, entry band, target band, invalidation level. No candlesticks above the fold.

**Below fold:** price chart (1Y default, engine invalidation drawn as a horizontal line that *moves with thesis updates*); financials snapshot (only metrics the thesis references); news & filings (thesis-filtered); reasoning drawer (Q9); thesis change history.

**What makes users trust enough to act:** *visible thesis change history*. Every engine view update is logged: "May 2: Working → Strong, driver: Q1 hyperscaler capex guidance." User sees how the engine reasoned over time, including misses. Trust-builder no other fintech AI does, because most are too embarrassed to show their misses.

**Defending the weakest claim:** "Past misses will scare users." It will scare *fast-money* users away. It will deeply earn *long-horizon* users. That is the trade we are making.

## Q6. Options experience

**Options need a different verb namespace. `BUY CALL` and `SELL PUT` on a card are slot-machine UI.**

Proposed: **single verb `STRUCTURE`**, with the structure type as a sub-label.

```
STRUCTURE  ·  Defined-risk bullish  ·  NVDA
─────────────────────────────────────────────
Long call vertical  ·  $175 / $190  ·  Jun 21
Net debit ~$4.20  ·  Max loss $4.20  ·  Max gain $10.80
Breakeven $179.20  ·  IV rank 42  ·  POP est. 38%
```

Key principles:

- **Loss is named first.** "Max loss $4.20" appears before "max gain $10.80." Inverts the gambling pattern.
- **No naked options ever shown to non-pro tier.** A naked short put is hidden behind a `Show advanced structures` toggle that requires explicit acknowledgement of margin risk.
- **IV rank and probability of profit are required fields**, not optional. Hiding them is the WSB pattern.
- **No "ROLL" verb.** Rolling is a mid-trade adjustment; surfacing it as a card encourages fiddling. If the engine wants to roll, it generates a `STRUCTURE adjust` card with full re-justification.
- **Beginner protection:** the first time a user sees an options card, a 3-screen primer interrupts. "Options can lose 100% of premium. Spreads cap loss. Naked shorts can lose more than premium." Three checkboxes, then unlocked.

**Risk surfacing:** every options card carries a *risk dot* — three sizes (small = defined risk, medium = naked premium, large = naked directional). The *only* color-coded element in the entire system, and only ever amber or red. Never green. No "low risk" green dot — even defined-risk has risk.

**Defending the weakest claim:** "STRUCTURE is jargon." Yes — and that friction is the point. Options *are* jargon. Pretending they're casual ("Buy a call!") is how Robinhood killed people. A user who can't get past STRUCTURE shouldn't trade options.

## Q7. Trust safeguards

Ten enforceable safeguards, each unit-testable:

1. **Max 5 cards/day in the hero.** Renderer-enforced; surplus goes to `/Ideas`.
2. **Max 2 `Conviction` cards per user per week.** Server-side; excess demoted.
3. **No card without an invalidation level.** Schema-required; missing = card discarded.
4. **No card without a horizon.** Same.
5. **No verb without thesis ≥ 80 chars.** Stub theses suppressed.
6. **Decision diet:** > 8 cards opened in 24h → next card becomes `Decision rest` interstitial: "You've reviewed a lot today. The engine isn't going anywhere."
7. **Confidence half-life enforced.** Every card has a decay clock; expired cards auto-demote.
8. **No green/red below saturation 60.** Conviction colors clamped to `hsl(*, ≤60%, *)`.
9. **No motion above 240ms or > 8px translation.** Blocks pulsing badges, ticker scrolls, sparkle effects.
10. **Weekly Calibration card:** "12 of last 30 `Strong` cards hit invalidation. Strong tier calibrated 60% — below target." Self-policing transparency.

**Edit to brief's preliminary list:** "Hero with > 5 actions" — tighten to >3 specifically for the hero. Five is too many decisions per viewport.

## Q8. Visual system

**Survives:** conviction *rings* (single ring, four fill states), verb badges (as labels only, monochrome), layered cards (single layer max, no stacked-paper effect — that's casino), the 8px grid.

**Dies:** conviction *bars* (linear progress bars read as "loading" / "battery low"), gradients (every gradient is a casino tell), conviction tints (background-color cards that shift hue with confidence — this is the actual hype machine pattern from Atom and Composer), score glyphs (any decorative score icon — you don't put a glyph on a number).

**Missing:** *typography hierarchy at three sizes only*. 24/16/13/11 — pick four sizes and never deviate. Most fintech apps fail on font-size proliferation; we lock to four. Body copy is `Inter 14px / 1.55 line-height / -0.005em tracking`. Headlines are `Söhne 24px / 1.15 / -0.02em` or fall back to `Inter`. No display fonts, no serif accents, no italic.

**Color tokens:**
- Background: `#0B0D10`, `#0F1115`, `#13161B` (three depth levels max)
- Text: `#F4F5F7`, `#9CA3AF`, `#6B7280` (high/mid/low)
- Conviction tint (the only "color"): `#7B8CFF` at 8% opacity for `Strong+`, applied as a 1px left border on the card, never as fill
- Risk red: `#C24A4A` (desaturated, not `#FF0000`)
- Never used: pure green (`#00FF00`), neon pink, electric blue gradients

**Defending the weakest claim:** "Monochrome is boring, the product won't feel premium." Wrong direction. Bloomberg Terminal is monochrome. Linear is monochrome. Stripe is monochrome. Premium = restraint. Cheap = chromatic.

## Q9. AI reasoning drawer

The drawer replaces "See the working" *only at the card surface*. Layer-3 stays as the engine escape hatch (separate concern, locked).

**Drawer contents, top-to-bottom:**

1. **Plain-language thesis recap (60 words).** Not a list of factors — a paragraph.
2. **Three drivers, three counters.** Bulleted, each one sentence. The *counters* matter: showing them is the trust-building move.
3. **What changed since the last card.** "Promoted from Working → Strong on May 2 because hyperscaler capex guide came in at +22% vs 18% expected."
4. **Calibration line.** "Current `Strong` tier hit rate: 60% (rolling 90d). Below 70% target."
5. **Engine version + last retrain date.** Tiny grey line at the bottom. `Engine v2.3.1 · last retrained Apr 28`.

**Hidden by default (require explicit "Show technical detail" tap):** factor weights, model class, backtest stats, IC decay curves, confusion matrices.

**Never shown anywhere:** raw probabilities to 4 decimal places, individual feature SHAP values per card (they're noise to a non-quant user), promotional language ("our model outperforms"). No marketing in the drawer. Ever.

**Defending the weakest claim:** "The calibration line will undermine confidence." That's the point. A copilot that admits its hit rate is more trustworthy than one that doesn't. If the rate is too embarrassing to show, the product isn't ready to ship.

## Q10. Biggest failure modes

**Top 3, in order of likelihood:**

1. **Verb gravity.** UX-10 ships with seven verbs; within two sprints, PMs ship micro-verbs (`NIBBLE`, `RIDE`, `EXIT 50%`) because the namespace expanded surface area. Product becomes a verb-taxonomy debate; engine becomes a verb-emission machine. We are M1 with worse copy. *Mitigation:* ship three. Resist expansion for 6 months.

2. **Confidence inflation.** Engine learns `Conviction` cards drive engagement. PMs/engineers tune thresholds down. Within a quarter, 40% of cards are `Strong+`. Tier system means nothing. *Mitigation:* hard rate-limit at the renderer (max 2 Conviction/week/user), with a public tier-distribution dashboard. If `Conviction` > 4% of all cards in a month, alert fires.

3. **Cockpit cosplay.** Beginners open the Research Cockpit, see price ladder + thesis triplet + financials, feel *qualified* to act on stocks they shouldn't hold. UX-10 makes them feel like analysts. They lose paper, then real money. *Mitigation:* horizon-gating. Beginners see the Cockpit but `OPEN` is gated behind a 24h "consideration window" — mark intent today, paper-execution lands tomorrow. Friction = thinking time.

**Honorable mention:** *generic stock-picker drift* — within a year, someone proposes reskinning into a "smart Yahoo Finance." Differentiators get watered down because they reduce DAU. *Mitigation:* lock Q7 safeguards as engineering invariants, not product preferences. Invariants survive PMs.

## Q11. Synthesis priorities

Top 5 for the master doc, ranked:

1. **Three-verb system + tier-with-decay confidence.** These two together prevent the casino drift. Everything else is downstream. Phase 10A.
2. **ActionCard contract with invalidation-above-target + horizon required.** The card is the atom of the system; if the atom is structurally honest, the rest can be too. Phase 10A.
3. **Research Cockpit as the core surface, with thesis change history.** The Stream is a feed; the Cockpit is where trust is built. Without history, we are not a copilot, we are a generator. Phase 10B.
4. **Trust safeguards as engineering invariants, not product copy.** The 10 safeguards in Q7 must be code-enforced, with tests. If a future PM tries to ship a `Provisional` tier that fires 30 cards a day, the schema rejects it. Phase 10C, parallel.
5. **Options as `STRUCTURE` with named risk first.** Options is where every fintech goes to die a casino death. Locking the verb namespace and the loss-first ordering before launch is cheaper than retrofitting it after WSB notices us. Phase 10D.

**Deprioritized vs. likely group consensus:** I would *not* prioritize the visual system polish (gradients, glyphs, motion). Those are Phase 10G+ at the earliest. If we get the verbs, tiers, card contract, cockpit, and safeguards right, the visual system will fall out naturally. If we get them wrong, no amount of polish saves us.
