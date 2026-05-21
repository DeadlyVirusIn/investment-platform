# Phase UI-1 — next-actions proposals (review-only)

**Status**: 4 proposals for review. No implementation.
**Scope**: only the 5 actions approved in the user's Day-12-review acceptance.
**Posture**: every word the user sees is sourced from a locked artifact (vocabulary table, banner copy module, or factual DB value). Wording can be revised; structure stays.

---

## PROPOSAL 1 — Revised honest-absence copy

### Problem (Sonnet)

Current copy:

| State | Current short | Current long |
|-------|-------------|------------|
| `honest_absence` (404) | "Part of this is still being built" | "The AI didn't produce structured reasoning for this decision. We won't substitute one." |
| `research_preview` | "Part of this is still being built" | "This is a research preview. Reasoning attaches once the AI acts on it." |

Problems:
1. "Still being built" reads as platform-incompleteness ("alpha software")
2. "We won't substitute one" is phrased in the negative — tells user what we WON'T do
3. "Structured reasoning" exposes a developer concept

### Constitutional constraint (Opus)

The COPY IS LOCKED in `apps/web/src/components/decisions/ReasoningCard.tsx` constants (mirrored from `apps/api/src/system_state/truth_banners.py`). The LOCK STRUCTURE is constitutional. The WORDING within the lock is operational.

Acceptable changes: rewrite the strings.
Forbidden changes: source the strings from anywhere other than a locked module; allow runtime substitution; introduce confidence framing; promise outcomes.

### Three options for review

#### Option A — "no clear read" framing (Sonnet's direction)

```ts
const ABSENCE_SHORT = "We don't have a clear read on this one";
const ABSENCE_LONG =
  "Some trades have a clean structural pattern the AI can describe. "
  + "This one doesn't. The trade is in your portfolio; we don't have "
  + "a story to tell about it.";

const ABSENCE_RESEARCH_PREVIEW =
  "The AI is considering this name but hasn't acted on it yet. "
  + "When it does, we'll show how it read the setup.";
```

**Tone**: deliberate restraint, conversational without losing precision.
**Pros**: addresses Sonnet's "alpha software" risk; signals that absence is a behavior, not a defect.
**Cons**: longer; "we don't have a story to tell" might still read as deflection to skeptical user.

#### Option B — direct attribution framing

```ts
const ABSENCE_SHORT = "No structural reasoning available";
const ABSENCE_LONG =
  "The AI's reasoning system requires a recognizable setup pattern "
  + "to produce a structured explanation. This trade doesn't match one. "
  + "Rather than write a generic story, we leave the explanation blank.";

const ABSENCE_RESEARCH_PREVIEW =
  "This pick is under research. The reasoning attaches when the AI "
  + "moves from considering to acting.";
```

**Tone**: clinical, mechanism-revealing.
**Pros**: explicit about WHY absence happens; user learns the system's behavior.
**Cons**: "structural reasoning" still uses a developer concept; longer onboarding load.

#### Option C — minimal honest framing

```ts
const ABSENCE_SHORT = "The AI made this call without a clean story";
const ABSENCE_LONG =
  "Sometimes the AI acts on a mix of signals that don't form a "
  + "recognizable setup. The trade happened; we don't have a clean "
  + "explanation, and we won't invent one.";

const ABSENCE_RESEARCH_PREVIEW =
  "Research-only. The AI is watching this name. If it acts, the "
  + "reasoning will appear here.";
```

**Tone**: shorter, accepts ambiguity directly, ends with the no-fabrication principle.
**Pros**: most honest framing; turns the absence into a virtue ("won't invent one"); shortest.
**Cons**: "without a clean story" might still feel like "AI failed to explain itself" to a low-trust user.

### Comparison matrix

| Dimension | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| Avoids "still being built" | YES | YES | YES |
| Signals deliberate behavior | YES (strongest) | YES | YES |
| Length (chars) | ~180 | ~210 | ~150 |
| Jargon (developer-leaking) | low | medium | low |
| Tone match to architecture | warm | clinical | direct |
| Explicit no-fabrication | implicit | explicit | EXPLICIT |
| Risk: still read as defect | low-medium | low | medium |
| Sonnet ranking (predicted) | 1 | 3 | 2 |
| Opus ranking (predicted) | 2 | 1 | 3 |
| Gemini ranking (predicted) | 3 (longest) | 2 | 1 (shortest) |

### Recommendation

**Option A as the user-facing default.** Closest to Sonnet's direction. Warm without softening the truth. The "we don't have a story to tell about it" framing makes the absence sound LIKE A CHOICE rather than A FAILURE — exactly the perception shift we need.

Option C is the runner-up if you want maximum brevity.

Option B is most accurate but most clinical — recommended only if the audience skews technical.

### Files touched (when implementing)

- `apps/web/src/components/decisions/ReasoningCard.tsx` — 3 string constants
- `apps/api/src/system_state/truth_banners.py` — optionally mirror for backend consistency (recommended)

### Out of scope for this proposal

- No structural change to `ReasoningCard`
- No new card states
- No banner-priority changes
- No additional fields rendered
- No onboarding card (separate deliberate decision)

---

## PROPOSAL 2 — PickModal confidence removal diff

### Problem (Codex / Opus / Sonnet consensus)

Current code at `apps/web/src/components/picks/PickModal.tsx:248-252`:

```tsx
{/* Recommendation — big colored badge */}
<section className="pick-modal-section" data-test="pick-modal-recommendation">
  <h4>Recommendation</h4>
  <div className="pick-modal-action-row">
    <span className="pick-modal-action-badge">{action}</span>
    <span><strong>{actionTitle(action)}</strong></span>
    <span>· {confidenceLabel(confidence)} confidence ({fmtConfidencePct(confidence)})</span>
  </div>
</section>
```

Issues:
- `fmtConfidencePct(confidence)` renders a percentage ("62%") which functions as confidence theater
- The percentage gives an impression of quantitative AI certainty that the system does not have
- Sonnet ranks this as the single most damaging artifact in PickModal
- Phase L Tier-A forbidden phrase list explicitly forbids "we're confident" / "we're sure" — the same constitutional spirit applies to "AI confidence: 62%"

### Three diff options

#### Option A — REMOVE percentage AND label

```tsx
<div className="pick-modal-action-row">
  <span className="pick-modal-action-badge">{action}</span>
  <span><strong>{actionTitle(action)}</strong></span>
</div>
```

**Effect**: only the action badge and title remain. No confidence framing anywhere.
**Cons**: loses ALL conviction context; user has no signal whether this is high-conviction Buy or marginal.
**Aligned with**: strict constitutional reading.

#### Option B — REMOVE percentage, KEEP qualitative label

```tsx
<div className="pick-modal-action-row">
  <span className="pick-modal-action-badge">{action}</span>
  <span><strong>{actionTitle(action)}</strong></span>
  {confidenceLabel(confidence) && (
    <span>· {confidenceLabel(confidence)} conviction</span>
  )}
</div>
```

**Changes**:
- `fmtConfidencePct(confidence)` call REMOVED
- `confidenceLabel(confidence)` retained (returns one of "Low" / "Medium" / "High" — already in `vocabulary_entry.confidence_label`)
- Rephrased "confidence" → "conviction" (matches engine's `Recommendation.conviction` field name; less psychometric framing)

**Effect**: user sees "Medium conviction" instead of "Medium confidence (62%)".
**Pros**: preserves rough conviction signal without false precision; "conviction" reframes from "AI is X% sure" to "engine's conviction score"; the qualitative label is engine-provided (not frontend-generated).
**Cons**: still uses a confidence-adjacent term.
**Aligned with**: Codex's "either remove or document why exempt"; Sonnet's "keep qualitative label only"; Opus's tonal-coherence concern.

#### Option C — REMOVE everything, ADD a structured chip

```tsx
<div className="pick-modal-action-row">
  <span className="pick-modal-action-badge">{action}</span>
  <span><strong>{actionTitle(action)}</strong></span>
  {confidence && (
    <span
      className="u-chip u-chip-neutral"
      title={`Engine conviction band: ${confidenceLabel(confidence)}`}
    >
      Conviction: {confidenceLabel(confidence)}
    </span>
  )}
</div>
```

**Effect**: explicit chip styling, label-only, hover tooltip clarifies "engine conviction band" (not AI certainty).
**Pros**: visually demotes the conviction signal from prose to chip; tooltip makes the source explicit.
**Cons**: more LOC; new chip pattern.

### Comparison matrix

| Dimension | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| Removes percentage | YES | YES | YES |
| Removes "confidence" word | YES | YES (reframed) | YES (reframed) |
| Preserves engine conviction signal | NO | YES (qualitative) | YES (chip) |
| LOC delta | -1 line | -0 net | +5 lines |
| Risk: user loses context | HIGH | LOW | LOW |
| Risk: confidence theater regression | NONE | LOW | NONE |
| Codex ranking (predicted) | 2 | 1 | 3 |
| Opus ranking (predicted) | 1 | 2 | 3 |
| Sonnet ranking (predicted) | 3 | 1 | 2 |

### Recommendation

**Option B**. Minimal change, preserves the qualitative conviction band (which IS a real engine output, not frontend-generated), eliminates the false-precision percentage, and reframes the language away from "AI confidence."

The qualitative label `Low / Medium / High` is engine-derived (from `candidate_idea.factor_breakdown.confidence_label`). It survives constitutional review because it's structured engine state, not a fabricated frontend percentage. Rendering it as "Medium conviction" rather than "Medium confidence (62%)" removes the false-precision implication.

### Verification after implementation

```bash
grep -n "fmtConfidencePct\|confidence (" apps/web/src/components/picks/PickModal.tsx
# Must be 0 hits.
```

### Out of scope for this proposal

- No removal of `Pick.confidence` from the backend type — engine still emits it; we just don't render the percentage
- No removal of `fmtConfidencePct` helper from `lib/picks/api.ts` — function survives in case it's used elsewhere (separate audit)
- No new confidence-rendering UI elsewhere

---

## PROPOSAL 3 — Minimal CI lint workflow

### Problem (Codex / all reviewers agree)

No `.github/workflows/` directory exists. Two lint scripts exist:
- `infra/ci/constitutional_checklist/forbidden_phrases.py`
- `infra/ci/constitutional_checklist/resolver_anchor_lint.py`

Neither runs automatically. A PR could land a Tier-A phrase or break the resolver anchor with no automated gate.

Snapshot suite exists as `apps/api/tests/unit/test_reasoning_envelope_snapshots.py` — runnable as `python <file>`, returns rc=0/1.

### Proposed workflow scope (minimal)

File: `.github/workflows/phase_l_lint.yml`

```yaml
name: Phase L constitutional lints
on:
  pull_request:
    branches: [main, phase-1/ledger]
  push:
    branches: [main]

jobs:
  lints:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Forbidden-phrase lint
        run: python infra/ci/constitutional_checklist/forbidden_phrases.py
      - name: Resolver-anchor lint
        run: python infra/ci/constitutional_checklist/resolver_anchor_lint.py
      - name: Reasoning snapshot suite
        run: PYTHONPATH=. python apps/api/tests/unit/test_reasoning_envelope_snapshots.py
```

### What it does

- Runs on every PR targeting `main` or the active branch
- Runs on every push to `main`
- Three sequential checks, each fails the job on rc=1
- No Docker, no DB, no compose — pure Python script execution
- No code coverage, no test framework wrapper, no build, no deploy

### What it deliberately does NOT do

- No type-check (would require Node.js setup; defer until later)
- No web build (defer)
- No backend Docker build (defer)
- No alembic check (defer)
- No options pages or other lints
- No security scan, dependency audit, SBOM, license check
- No deploy preview

### Effort

- 1 YAML file, ~25 lines
- 0 new Python code
- Existing scripts work as-is
- Validation: confirm GitHub Actions runs the workflow; deliberately introduce a Tier-A phrase in a draft PR and confirm CI red

### Risks

- Snapshot suite requires `PYTHONPATH=.` and imports from `apps.api.src.reasoning.*`. May need `pip install -e .` step or similar. Worth a one-shot validation on a draft PR before merging.
- GitHub Actions runtime ~30 seconds total — acceptable.

### Recommendation

Ship as proposed. Minimal scope, highest leverage. Extends naturally to additional checks as needed (e.g. when `pytest` is added, the snapshot suite can convert to a pytest test).

### Out of scope for this proposal

- No GitHub Actions runner self-hosting
- No matrix builds (Python versions, OS)
- No caching
- No GitHub status badge in README

---

## PROPOSAL 4 — Structured novice walkthrough plan

### Problem (Gemini / Sonnet)

Zero external user observation in 12 days of Phase L work. The reasoning system's most distinctive virtue (honest absence) has never been read by a person without architectural context.

### Recruitment

- 1 participant (this is the smallest defensible sample for the first observation)
- Not someone who has seen the product before
- Demographic match for the intended novice user — adult, has used Robinhood or similar consumer trading app, NOT a quant or developer
- Compensation: $50 gift card (industry-standard 30-minute test rate)
- Recruit via: existing personal network, NextDoor post, Craigslist research-participation listing, or `r/SampleSize`

### Setup

- 30 minutes scheduled, 40 minutes allocated (10 min buffer)
- Video call with screen-share recording enabled (Loom / Zoom record)
- Browser: Chrome / Firefox at standard window size, NOT mobile
- Participant uses their OWN computer (not facilitator's) — reduces "showcase" bias
- Facilitator (you or a designated reviewer) joins muted-mic-on-camera-on but doesn't lead the participant

### Pre-test script (2 min)

> "I'm going to ask you to use a product I've been working on. There are no right or wrong answers. I'm going to mostly stay quiet. If you have questions, say them out loud — I may or may not answer depending on whether the answer would bias the test. If you get stuck, that's data. We want to learn what's confusing, not test whether you're smart."

### Tasks (20 min total)

1. **Open the platform.** Hand them the URL. Tell them: "Imagine a friend told you this is an AI that picks stocks. Take 2 minutes. Tell me what you see."
   - Observe: where do their eyes go first? Where do they click first?
   - Listen for: confusion, surprise, dismissal.

2. **Click ONE pick.** "Click any one of these recommendations. Tell me what you see."
   - Observe: do they read the modal top-to-bottom? Skip to the price? Scroll?
   - Listen for: "what does this mean," "what is this number," "why is this here."
   - **Critical observation point**: do they read the ReasoningCard "AI's reasoning" section? Do they engage with it or skip it? If they skip, why?

3. **Read the honest-absence card aloud.** Direct prompt: "Can you read the section called 'AI's reasoning' out loud, then tell me what you think it means?"
   - **THIS IS THE PRIMARY TEST**. Listen exactly to what they say.
   - Failure mode: "Oh, it's not done yet" → product confirmed reads as incomplete
   - Success mode: "Oh, the AI just doesn't have a clear story here — that's actually kind of refreshing" → product confirmed reads as deliberate

4. **Decision pressure.** "If you had $1000 to invest right now, would you act on this AI's pick? Why or why not?"
   - Listen for: what tipped their decision? Did the AI's reasoning play any role? Did they ignore it entirely?

5. **Comparison.** "What would you want to see in this modal that's not here?"
   - Listen for: confidence scores, price targets, news, analyst ratings, social proof.
   - Resist defending the product. Just listen.

### Closing (5 min)

> "Last questions. (1) Would you sign up for this if it were a real product? (2) Would you trust it to make trades for you? (3) On a scale of 1-10, how clearly did the AI explain what it was doing?"

### What to record

- Full screen recording with audio
- Facilitator notes during session: timestamps + what participant said
- Post-session: 30-min reflection memo summarizing observations
- Save to `docs/research/user_observations/<date>_<participant_id>.md`

### Success criteria (set BEFORE the test)

**The walkthrough was useful IF**:
- We learn what the participant actually thinks of the honest-absence card
- We learn whether the participant noticed the deterministic reasoning at all
- We learn whether the deterministic reasoning influenced their decision
- We get one clear "this thing confused me" data point

**The walkthrough is INCONCLUSIVE if**:
- Participant is too polite to surface real friction
- Participant has too much investing knowledge (becomes operator-perspective)
- Technical issues consume more than 5 minutes

**The walkthrough is a STRONG SIGNAL if**:
- Participant comments unprompted on the AI's reasoning (positive OR negative)
- Participant compares unfavorably to another product they know
- Participant correctly interprets honest-absence as a feature (validates the thesis)
- Participant misreads honest-absence as a defect (challenges the thesis)

### Anti-pattern: do not do these things

- Do not defend the product mid-test
- Do not explain features the participant hasn't found
- Do not skip the comparison question (most painful but most useful)
- Do not interpret behavior in the moment — record raw, analyze after
- Do not iterate UI based on a single user. ONE user is a hypothesis, not a verdict.

### Output

After test:
1. Raw recording stored locally
2. Memo at `docs/research/user_observations/<date>_user1.md` with:
   - 5 most surprising observations
   - 3 quotes verbatim
   - "Honest-absence interpretation" — did they read it as deliberate or defective?
   - "Recommended next test" — what to validate next based on what we learned
3. Post-test conversation with stakeholders (you, me, anyone else interested)

### Decision criteria after first walkthrough

- If participant reads honest absence as DELIBERATE → architecture/UX is winning; proceed with UI-2
- If participant reads honest absence as DEFECT → highest priority is fixing the comprehension layer (onboarding card + copy revision); pause UI-2
- If participant is indifferent / didn't engage → the AI reasoning section is invisible to them; bigger problem than honest-absence wording

### Effort

- Recruitment: 1-3 hours over a few days
- Session: 40 minutes
- Memo: 1 hour
- Total: ~3-5 hours

### Out of scope for this proposal

- No multi-participant studies (defer until single-user observation surfaces hypotheses worth testing at scale)
- No A/B testing of copy variants (defer; need consensus on Option A/B/C from Proposal 1 first)
- No quantitative metrics (no analytics infrastructure yet)
- No remote async usability tests (defer)

---

## Summary

| Proposal | Recommended option | Effort | Risk |
|----------|---------------------|--------|------|
| 1. Honest-absence copy | Option A ("no clear read" framing) | ~30 min | LOW — copy-only |
| 2. PickModal confidence removal | Option B (remove %, keep qualitative as "conviction") | ~15 min | LOW — single section |
| 3. CI lint workflow | Ship as proposed | ~30 min + draft-PR validation | LOW |
| 4. Novice walkthrough | Single-participant, structured | 3-5 hr | NONE (observation only) |

Total implementation effort if all 4 approved: ~5-6 hours.

### Order of operations (if all approved)

1. **CI lint workflow** FIRST — prevents regression on any subsequent change
2. **PickModal confidence removal** — small, isolated diff
3. **Honest-absence copy revision** — small, isolated diff
4. **Novice walkthrough** — runs against the updated UI, validates the perception shift

Items 2 + 3 should ship before the walkthrough so the participant sees the cleaned UI, not the half-cleaned one.

### What's deferred (not in this proposal set)

- Truth banner global slot (UI-2)
- State chips (UI-2)
- ReasoningTimeline (UI-2)
- OpsReasoningPanel (UI-2)
- Vocabulary glossary tooltip (UI-2)
- Concentration-visibility affordance (UI-2 / UI-1 fix)
- Per-position context strip (UI-2)
- Source-pill renames (Replay → Historical, etc.) (UI-2 candidate)
- Breadth ETL implementation (substrate work)
- Earnings provider activation (blocked, separate dep)
- Decisions.tsx refactor (deferred)
- Copilot view archive (deferred)
- 3 remaining freeform-prose surfaces (Briefing, Decisions state panel, ActionCard) (UI-2)

### What needs your decision

Per proposal:

1. Copy option **A / B / C** (recommendation: A)
2. PickModal option **A / B / C** (recommendation: B)
3. CI workflow scope: **ship as proposed** or **expand to include type-check / web build** (recommendation: ship as proposed)
4. Walkthrough: **proceed with recruitment** or **defer until UI changes ship** (recommendation: ship UI changes FIRST, then walkthrough)
