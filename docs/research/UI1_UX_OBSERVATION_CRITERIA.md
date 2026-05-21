# Phase UI-1 — UX Observation Criteria

**Purpose**: define what an operator or novice user should be observed for once they interact with Phase UI-1 reasoning surfaces.
**Status**: Observation criteria. No implementation.
**Posture**: assume the user is honest, the architecture is correct, and any discomfort users feel is a SIGNAL to investigate — not a prompt to fabricate explanations.

## Top-level question to answer

Does the UI remain trustworthy, understandable, and operationally calm once real users/operators interact with deterministic reasoning at scale?

## The 6 ReasoningCard states — what to watch for

The component has 6 explicit states. Each can fail differently.

### State 1: `research_preview` (caller asserted no decision yet)

**Visible to**: PickModal only (every pick is research-stage until acted on)

**Failure modes to watch**:
- Novice reads "Part of this is still being built" and thinks the platform itself is incomplete
- Novice doesn't understand that "research preview" means "AI hasn't traded this yet, only thinking about it"
- Confusion about WHY a research preview exists if the platform shows a pick recommendation

**What good looks like**:
- Novice understands: "AI suggested this, but hasn't committed. Reasoning will appear once it acts."
- No follow-up complaint about "the AI didn't explain itself"

### State 2: `no_trade_id`

**Visible when**: caller passed `null` without `researchPreview` flag

**Failure modes to watch**:
- Should never appear in normal use — indicates caller bug
- If observed, log + fix; should not be a UX-visible state in steady operation

### State 3: `loading`

**Visible when**: fetch in flight

**Failure modes to watch**:
- Loading persists > 1 second (perf regression — backend renderer is 250+ rps, should be sub-50ms)
- Layout shift when card resolves (would distract)
- User clicks away before render completes

### State 4: `error` (non-2xx-non-404)

**Visible when**: API fails (500 / network)

**Failure modes to watch**:
- User reads "The reasoning service didn't respond" and assumes the TRADE failed
- User panics about position validity
- User retries excessively

**What good looks like**:
- The card's body line ("The trade itself is intact — only the explanation is unavailable right now.") deflects the panic correctly

### State 5: `honest_absence` (404)

**Visible when**: backend has no envelope for this paper_trade

**Failure modes to watch (most critical)**:
- User assumes the AI is "lying" or "hiding"
- User asks "why won't it tell me what it did?"
- User trusts the platform LESS because of absence (the opposite of what we want)
- User compensates by inventing their own explanation
- User abandons the platform feeling unsupported

**What good looks like**:
- User reads "The AI didn't produce structured reasoning for this decision. We won't substitute one." and understands this is an honest disclosure, not a defect
- User trusts the platform MORE because it doesn't fabricate

**Single most important UX observation across all of UI-1.** If users misread honest absence as a defect, Phase UI-2 needs a banner / glossary entry / first-run education flow.

### State 6: `rendered` (envelope present)

**Visible when**: backend returns a real envelope

**Failure modes to watch**:
- User scans the setup sentence and skips because it's generic-sounding
- User reads identical text on consecutive positions and assumes the UI is broken (the "truthful collapse" UX risk noted in UI1-R.1)
- User looks for confidence percentage and is confused when absent
- User clicks "Show structured data" (operator variant) and finds the vocabulary opaque

**What good looks like**:
- User reads the setup, accepts it, moves on
- User notices when uncertainty markers DO fire and pays appropriate attention
- Operator clicks structured data and finds canonical names usable

## The "truthful collapse" UX risk

**The most important UX finding from UI1-R.1**: 5 real envelopes rendered identical text. This is correct architectural behavior — the AI's actual strategy concentrated those 5 trades into the same skeleton+slot+marker shape, so they collapse to one canonical hash.

But to a user clicking through 5 positions, the SAME reasoning appearing 5 times is suspicious. They might think:
- the system is broken
- the system is lazy
- the system is hiding something
- they're looking at the wrong card

**Mitigation options for Phase UI-2 (DO NOT fabricate variety)**:
1. Add a small "Other positions sharing this reasoning: N" affordance — makes the collapse visible AS a fact, not a glitch
2. Show position-specific context alongside (asset symbol, fill date, P&L) — already does
3. Operator-variant: show the slot values that drove the choice — makes the truthful uniformity legible
4. Banner: "12 of today's 14 entries fired the same setup. The AI is currently running a concentrated regime-aligned book." — surfaces strategy concentration as a feature, not a hidden truth

DO NOT introduce variety by:
- Adding asset-specific prose
- Adding "this stock specifically because..." narration
- Adding randomized phrasing variations
- Adding per-position confidence delta

## Source pill — usability checks

**Full variant** (used inside cards): "Live" / "Replay" / "Backfill" / "Operator"

Watch for:
- Novice asks "what's the difference between Live and Replay?" — needs a tooltip or glossary
- Novice assumes "Replay" means "the AI is replaying my history" rather than "this is historical backtest data" — semantic clash

**Compact variant** (single letter, table rows): "L" / "R" / "B" / "O" with title tooltip

Watch for:
- Tooltip not appearing on touch devices (mobile)
- Compact chips read as decorative not informative
- Color-blind users miss the chip entirely against the row background

## Operator variant — collapsible structured data

When operator clicks "Show structured data":

Watch for:
- Operator scans skeleton_id and recognizes the canonical name OR doesn't
- Operator looks for the hash and uses it for cross-referencing (good — that's its purpose)
- Operator reads slot_fills and asks "what is `breadth_broadening`?" — needs glossary
- Operator wants to copy the envelope hash for an audit ticket — affordance test

## Novice comprehension WITHOUT confidence widgets

Phase L constitution explicitly forbids "AI is X% sure" framing. Novice users may notice the absence:

Watch for:
- "How confident is the AI?" question
- User searches for a confidence percentage and gives up
- User invents their own confidence interpretation from setup sentence tone
- User asks operator "should I trust this trade?" externally

**What good looks like**:
- User reads the marker list and understands "we've only seen this setup a handful of times" as the honest version of "low confidence"
- User does NOT ask for a number — the qualitative framing satisfies

## Live-cron divergence vs replay behavior

Once 2026-05-19 03:30 UTC fires (or any subsequent live cron), check:

- Are live envelopes hashed identically to replay envelopes for the same canonical content? (Architecture says yes, but UX must verify.)
- Does the source pill change from "Replay" to "Live" on new rows without UI hiccup?
- Do telemetry rows match the live trade count in the UI?
- Does the gaps endpoint shrink as live envelopes attach?

## Operator friction notes — what to log

When an operator runs the system over multiple sessions:

1. **Time-to-comprehension** per card: did they read setup + thesis + markers before clicking off, or skip?
2. **Question frequency**: how often do they ask about the same card concept (skeleton names, marker meanings)?
3. **Trust events**: any moment they doubted the system because of UI behavior?
4. **Workflow blockers**: any step where the UI didn't give them what they needed?
5. **Compensatory behavior**: did they open a second tab, search elsewhere, ask a teammate?

## Calm-operational signals

Phase L's tonal goal is "carefully honest, never apologetic, never inflated." Observe whether the UI reads:

- Calm (not anxious)
- Honest (not promotional)
- Concrete (not vague)
- Operator-respectful (doesn't talk down)
- Novice-respectful (doesn't talk over)

If any of those fail, that's a tonal regression — fixable in copy without code, but worth catching.

## What is NOT being observed yet

- Truth banners (UI-2)
- State chips (UI-2)
- Coverage dashboards (UI-2)
- Timeline view (UI-2)
- Mobile usability
- Performance under low-bandwidth
- Accessibility compliance
- Internationalization

## Escalation criteria (per user directive)

Escalate ONLY if:
- Users misunderstand honest absence
- Old prose surfaces remain (the 3 documented in UI1_REVIEW_AUDIT.md don't count as regression — they were never in UI-1 scope)
- Source visibility causes confusion
- Deterministic rendering creates UX ambiguity
- Live-cron UI behavior diverges from replay behavior
