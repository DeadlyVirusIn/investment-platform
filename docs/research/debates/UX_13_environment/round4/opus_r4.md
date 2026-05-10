# Model: Claude Opus 4.7
## Round: 4

## Dispute 1 — Verb-glyph

**Resolution: split the difference cleanly. Hold (a) on the tile, adopt (b) on the page.**

UX-10/11/12 verb pill at 11px stays locked on the ConvictionTile schema. That lock is correct and it survives. **Separately**, Sonnet's 36pt (Duet) / 48pt (Solo) verb-GLYPH ships as a new page-chrome element, anchored at the fixed (x, y) just below the 40vh cut. Two visual categories: pill is schema element (data); glyph is page chrome (focal). They are the same word but different objects, like the small caption "FIG. 1" under a photo and the full headline above it.

Why this resolves the casino concern: the glyph is page chrome, not tile chrome. The user's eye trains on it as a *fixed page anchor* (Sonnet's verb-anchor-point R2 synthesis), not as a per-tile call-to-action. It's the only place "OPEN/HOLD/TRIM/EXIT" appears at large scale on the entire surface. Singular = restraint. The tile pill remains 11px and never grows.

Acceptance gate: A/B at 13C. If the 36pt glyph causes user-tested Codex-test failure ("user reads 4 tiles in 5s"), kill the glyph and revert to no-page-chrome-verb. If glyph helps the eye find the verb-anchor faster than 5s, keep.

## Dispute 2 — Halo

**Resolution: hold Solo-only at 4% amber.** Codex's anti-glow case is principled but the 4% Solo-only constraint is principled enough to coexist.

Codex's strongest line: "all glow is casino." Strong rule, wrong scope. Glow that signals state (mood-ring, conviction-density, action urgency) is casino. Glow that signals composition rarity is *atmospheric framing* — the same category as the 2.5% UX-12 stage tint, just localized to one room ~15% of the time. Wes Anderson centers a single window of light in a shot precisely because it does NOT happen every frame; that contrast IS the framing.

Concede to Codex: if the halo were present in Duet (60% of sessions) it WOULD be casino — the dose makes the difference. The 4% Solo-only narrowing is the entire defense. Document Codex's dissent as "if Solo runs more than 20% of sessions, the halo automatically transitions to casino territory and must be killed." Quantitative trigger.

## Dispute 3 — Hero anchor

**Resolution: hold left, but ALLOW right as a mode-conditional experiment in Solo only.**

LEFT-anchored hero in Duet is correct. F-pattern reading + posture-sentence-also-left + magazine spread tradition = 3-vs-1 wins decisively. Hold.

But Solo is different. In Solo the hero is 1.5× width and there is essentially nothing to its right except a single watchlist line. The negative well argument loses force when there's almost nothing to be a "well" against. Codex's right-anchored hero might actually work in Solo specifically — the eye lands on the posture (left), then the entire viewport center-right becomes the hero, with the verb-glyph crossing 40vh below it. The asymmetry inverts only in Solo.

Recommendation: lock LEFT for Duet (default ~60% of sessions). Allow RIGHT-anchored as Solo-only experiment. Test at 13C; if it tests well in Solo, keep; if not, revert to left across all rooms. This gives Codex's R1 contribution a concrete venue without breaking the Duet default.

## Single most important resolution recommendation

**Adopt Dispute 1 resolution.** The two-category verb (11px tile pill + 36/48pt page-chrome glyph) is the single highest-leverage move from the entire 4-round debate. It resolves Sonnet's strongest dissent without breaking any locked invariant, and it gives the page a literal focal anchor the user's eye trains on across weeks of opens. If Opus could only adopt one R4 resolution, this is it.
