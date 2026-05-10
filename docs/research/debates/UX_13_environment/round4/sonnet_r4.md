# Model: Sonnet 4.6
## Round: 4

## Dispute 1 — Verb-glyph at 36-48pt

**Holding the position, with sharpened framing.** I am 1-vs-3 on the score, but the master's locked language already concedes the substance: it documents the 36-48pt verb-glyph as a "future-experiment as page-chrome focal element distinct from tile schema verb-pill." That phrasing is correct and is the resolution. I push the master to harden it from "future-experiment" to **option (b) adopted as a parallel page-chrome category, gated to Solo + Duet only**.

The reason this is not bloat: Opus's R2 attack ("breaks UX-10 §3.2 verb pill spec, turns verb into largest visual element = casino") collapses on inspection. The UX-10 verb-pill is a **state label inside the ConvictionTile schema** at 11px monochrome. The UX-13 verb-glyph at 36/48pt is a **page-chrome focal anchor outside the tile**, sitting at the fixed (x,y) just below the 40vh cut. They are different objects at different layers in the rendering hierarchy. They do not collide in the DOM, in the schema, or in the user's reading model. The pill says "this tile's current verb is OPEN"; the glyph says "the AI's verdict for the day is OPEN." Same word, two layers.

Opus's R3 explicitly conceded this: *"a verb-GLYPH (different visual category from verb-pill) at 36pt is defensible as a page-chrome focal element distinct from the tile schema."* That is a 2-vs-2 on the substance once Opus's R3 concession is counted, not 1-vs-3. Gemini also supports the 36/48pt scale in R3 ("Sonnet and I advocate for a 36pt/48pt serif verb glyph outside the tile"). So the actual final tally is **Sonnet + Gemini for + Opus partial-yes + Codex against** — call it 2.5-vs-1.5, not 1-vs-3.

The casino objection is wrong because casino requires (a) saturated color, (b) motion, (c) state-mapped feedback. The verb-glyph has none: it is `var(--ux12-fg-secondary)` (already-locked), static, and renders the same word the pill does — it does not "react." It is a serif headline, not a slot machine display. Magazine front pages have one large headline word; nobody calls *The Economist*'s cover "casino."

**Recommendation:** master moves the verb-glyph from "future-experiment" status to **locked Phase 13C deliverable**, gated to Solo (48pt) and Duet (36pt). Anti-pattern #62 already protects against drift into nav/footer/chrome. That guard is sufficient.

---

## Dispute 2 — Halo

**Holding Solo-only at 4% amber.** Codex's principled objection deserves the documented dissent it has, but the lock is correct. Three reasons in tight form.

First, the casino threshold is empirically about *frequency × saturation × motion*, not presence. A 4% amber static radial that appears in ~15% of sessions, never animates, never state-maps, and is locked to the existing UX-12 amber family is below every casino threshold I can name in the design literature. Apple's macOS Sequoia menu-bar wash sits at ~3% saturation and reads as atmosphere. Stripe's marketing pages use 4-6% amber radials behind hero illustrations and read as editorial. Codex's "implementation drift" risk is real but is what anti-pattern #59-#61 exist to prevent — three guards (opacity ≤4%, color in amber family only, never in Duet/Field).

Second, killing the halo entirely removes the only environmental signal that distinguishes Solo from Duet at the atmosphere layer. Without it, Solo becomes "Duet but the hero is wider," which underweights the editorial significance of a Confirmed-tier singular call. The verb-glyph scale change (36pt → 48pt) does some of that work, but the halo is what makes Solo *feel* like a master shot rather than a wider Duet. Wes Anderson's lit-from-above frames are not casino because they are rare and uniform; daily glow is casino because it is constant feedback. Restraint is the entire mechanism.

Third, Codex's alternative — verb-glyph + hero-crosses-40vh + zone-level wash — has its own load-bearing weakness: if all three rooms use only zone-level wash, the AI has no way to *visually* distinguish "I am decisive today" from "I see a call and a counter" beyond column count. Column count is structural; halo is atmospheric. We need both registers.

**Recommendation:** master holds the lock as written. No change. Codex's anti-glow dissent stays documented in §2 D3 and anti-patterns #59-#61. If implementation drift occurs in 13A staging, the halo is the first thing to kill — but kill it on evidence, not on principle.

---

## Dispute 3 — Hero anchor

**Holding left-anchored. Conceding nothing here is reasonable.** The 3-vs-1 vote reflects the real cognitive science: F-pattern reading on Western copy is well-documented (Nielsen Norman Group, eye-tracking studies on financial publications spanning 20+ years). The left-anchored hero with negative well right matches every editorial reference we have invoked across three rounds — FT, NYT, Stratechery, Apple keynote pages, Linear's project headers. Codex's right-anchored argument ("user reads posture left → lands on conviction right") inverts the established mass-then-release flow; it would force the eye into a diagonal sweep that fights the natural F-scan and ends in the right gutter where there is nowhere to "exhale" to.

The investing-context modifier sharpens this further. Investing copy is consumed in editorial-tier seriousness mode (FT/Bloomberg/Stratechery), not advertising mode (where right-anchored hero with left-rail copy is sometimes used to surprise the eye). UX-13 is the former. Right-anchored hero would be a category error.

**Recommendation:** master holds the lock. Codex right-anchored stays as documented dissent in §2 D2. Do **not** experiment with right-anchored in staging — running both simultaneously would muddy the 5-second acceptance test, and we have no evidence that warrants the disruption. If the team later wants to test it, treat it as a separate post-13X experiment with its own validation cycle, not as an A/B inside UX-13 phasing.

---

## Single most important resolution recommendation

**Adopt Dispute 1.** Promote the 36-48pt verb-glyph from "future-experiment as page-chrome focal element" to **locked Phase 13C deliverable** in Solo + Duet. The halo (D2) and hero anchor (D3) are atmospheric and structural choices that the master already locks correctly; the verb-glyph is the one move that is *materially under-locked* and would change what the user sees in 13C delivery. Without it, the master ships three rooms with no focal typographic gravity instrument outside the tile schema, and the brief's "ONE opportunity should visually dominate" requirement falls entirely on column-span and halo — which is too much weight on too few instruments. With it, the verb-anchor-point lock (L2) gains its load-bearing object, and the room composition has a typographic anchor the eye can train on across sessions.
