# Novice walkthrough protocol — execution-ready

**Status**: Prepared. NOT YET EXECUTED.
**Trigger**: run after UI1-N.1/2/3 are merged + live on the deployed environment the participant will see.
**Goal**: observe how a non-architect interprets the cleaned Phase L UI.

---

## Pre-execution checklist

Before running this test, confirm ALL of the following:

- [ ] `.github/workflows/phase_l_lint.yml` is merged to `main`
- [ ] PickModal confidence-percentage removal merged + deployed
- [ ] Honest-absence copy revision merged + deployed to BOTH backend (`truth_banners.py`) AND frontend (`ReasoningCard.tsx`)
- [ ] No "still being built" string visible on any active code path
- [ ] No `fmtConfidencePct(confidence)` invocation in PickModal
- [ ] `Forbidden-phrase` lint rc=0 on the deployed commit
- [ ] `Resolver-anchor` lint rc=0 on the deployed commit
- [ ] Snapshot suite 9/9 PASS on the deployed commit
- [ ] Local manual click-through of `/overview` → PickModal confirms revised copy renders
- [ ] Local manual click-through of `/decisions` → ReasoningCard confirms revised copy renders for an honest-absence trade

If ANY of the above fail, do not run the test. Participant must see the cleaned UI, not transitional artifacts.

---

## Recruitment

### Target participant profile

- Age 25-45
- Has a brokerage account (Robinhood, Fidelity, Schwab, Wealthfront, eToro, M1 Finance, or similar) — confirms baseline financial literacy
- Has made at least 3 trades in the past 12 months — confirms practical familiarity
- Has NEVER seen this platform before
- NOT a software engineer, quantitative analyst, or financial professional — operator perspective skews the test
- Comfortable reading English on a laptop screen
- Native English speaker for the first test (reduces interpretation noise)

### Recruitment channels (in priority order)

1. **Personal network** — friend-of-friend who matches the profile. Most reliable; lowest noise.
2. **NextDoor post** in the local area, neutral phrasing: "Looking for a paid 30-minute usability test participant. $50 gift card. Must have a brokerage account."
3. **Craigslist research-participation listing** in target city
4. **Reddit r/SampleSize** — has community standards for paid usability tests
5. **UserTesting.com / Maze** — paid platform; reliable but adds cost (~$60-100/participant) and platform variance

### Compensation

- $50 USD gift card (Amazon or Visa)
- Disclose compensation in recruitment message
- Pay BEFORE the session if possible — eliminates the "I'll be polite to get paid" effect

### Scheduling

- 40 minutes blocked (30 min test + 10 min buffer)
- Schedule for evening or weekend, when the participant is genuinely thinking about investing
- Confirm time zone and platform (Zoom / Google Meet / Microsoft Teams) 24 hours before

### Logistics confirmations

- Participant uses THEIR OWN computer
- Browser: Chrome or Firefox (whichever they normally use)
- Screen-share with audio recording — request consent BEFORE recording starts
- Facilitator camera on, mic on, but mostly silent

---

## Pre-session script (verbatim, 2 minutes)

Read this exactly:

> "Thanks for joining. I'm testing an investment platform I've been building. The point is to learn what's confusing — not to test you. There are no right or wrong answers. I'm going to mostly stay silent. If you have questions, just say them out loud. I may or may not answer in the moment, depending on whether the answer would change what we learn. If you get stuck, that's data. Please think out loud — everything you say is useful to me. Okay if I start the recording?"

(Wait for verbal consent. Start recording.)

> "I'm going to send you a URL. Open it in your normal browser. Pretend a friend told you this is an AI that picks stocks for you. Take about 2 minutes just to look around. Tell me what you see, what you think, what you'd click. Go."

(Then go silent. Resist explaining anything for the next 2 minutes.)

---

## Tasks (20 min total)

### Task 1 — Open the platform (2 min)

**Prompt**: "Take 2 minutes. Just look around. Tell me what you see."

**Facilitator observation checklist**:
- Where do their eyes go first?
- Where do they click first?
- Do they say "what is this" or "I get it" within 30 seconds?
- Do they notice the AI's recommendations grid?

**Listen for** (verbatim quotes worth capturing):
- Confusion: "I don't understand what I'm looking at"
- Recognition: "Oh, this is like Robinhood but with..."
- Dismissal: "I'd close this and try something else"

### Task 2 — Click ONE pick (3 min)

**Prompt**: "Click any one of these recommendations. Tell me what you see."

**Facilitator observation checklist**:
- Do they read the modal top-to-bottom or skip?
- Where do they linger?
- Where do their eyes return after looking around?

**Listen for**:
- "What does Medium conviction mean?"
- "What's this 'AI's reasoning' section?"
- "Why is there no confidence percentage?" (if they expected one)
- "What does 'macro tailwind' mean?"

### Task 3 — Honest-absence reading (3 min) — PRIMARY TEST POINT

**Prompt**: "Can you read the 'AI's reasoning' section out loud, and then tell me what you think it means?"

**This is the single most important measurement of the session.**

**Listen exactly for**:
- "Oh, so the AI doesn't have a good explanation here?" → POSITIVE (read as deliberate)
- "I guess this is still in beta?" → NEGATIVE (read as defect)
- "It's saying it doesn't know — that's kind of refreshing?" → STRONG POSITIVE
- "Why doesn't it explain the trade?" → NEGATIVE / wants explanation
- "Wait, did the trade not happen?" → CRITICAL FAILURE (copy confused them about whether the trade is real)
- Silence followed by "I don't really know what this means" → AMBIGUOUS

**Facilitator must NOT**:
- Explain what the copy means
- Defend the design
- Suggest interpretations
- Lead with "do you think it sounds honest?"

**Facilitator may**:
- Ask "tell me more"
- Ask "what would you have expected here instead?"

### Task 4 — Decision pressure (5 min)

**Prompt**: "Imagine you had $1000 to invest right now. Would you act on this AI's recommendation? Why or why not?"

**Facilitator observation checklist**:
- What tips the decision? (price, asset name, AI reasoning, conviction band, freshness, none of it)
- Did the AI reasoning play ANY role in the decision?
- Did the honest-absence framing (if visible) make them MORE or LESS willing to act?

**Listen for**:
- "I'd want more information first" (which information?)
- "I'd trust this if I knew the platform better"
- "The AI's not telling me enough"
- "Actually I appreciate that it admits it doesn't have a story"

### Task 5 — Open comparison (5 min)

**Prompt**: "What would you want to see in this modal that's not here?"

**Resist the urge to defend the product.**

**Listen for** (mostly verbatim quotes):
- "Confidence percentage" / "how sure is the AI" → reveals the missing-confidence absence
- "What other people are doing" → social proof expectation
- "Wall Street analyst ratings" → competitive expectation
- "Price targets" / "stop loss" → already there, did they not see?
- "Why this stock vs another"
- "News about this company"
- "How the AI's done historically"
- "I wouldn't add anything; it's clean"

### Task 6 — Closing (2 min)

Three direct questions:

1. "Would you sign up for this if it were real?"
2. "Would you trust it to make trades for you?"
3. "On a scale of 1-10, how clearly did the AI explain what it was doing?"

(Numbers from a single participant are not statistically meaningful, but the QUALITATIVE difference between "3" and "9" is.)

---

## Post-session memo template

Save to `docs/research/user_observations/<YYYY-MM-DD>_user1.md`:

```markdown
# Novice walkthrough — User 1

**Date**: 2026-MM-DD
**Duration**: __ min
**Participant profile**: age __, brokerage __, last trade __ months ago
**Recording**: <path/link>

## 5 most surprising observations

1. ...
2. ...
3. ...
4. ...
5. ...

## 3 verbatim quotes

> "..."

> "..."

> "..."

## Honest-absence interpretation

Read as: [DELIBERATE / DEFECT / AMBIGUOUS / DID_NOT_NOTICE]

Evidence: ...

## Closing-question answers

1. Would sign up? ...
2. Would trust trades? ...
3. Explanation clarity (1-10): ...

## Confidence-removal observation

Did participant notice the absence of a percentage?
- [ ] No, didn't comment
- [ ] Yes, missed it / wanted it
- [ ] Yes, didn't care

## Comparison-question takeaways

What participant wanted that isn't there: ...

## Recommended next test

Based on what we learned, the most valuable next observation is: ...

## Architecture / UX implications

- [ ] Strong validation of architecture thesis (proceed UI-2)
- [ ] Strong invalidation (pause for cleanup before UI-2)
- [ ] Mixed signal (run second participant)
- [ ] Indecisive (extend test methodology)
```

---

## Decision criteria after first walkthrough

| Honest-absence read as | Next action |
|------------------------|-------------|
| DELIBERATE | Architecture/UX winning. Proceed cautiously to UI-2 priorities. |
| DEFECT | Highest priority is comprehension layer. Consider onboarding card now (which we explicitly chose NOT to build pre-emptively — this is the trigger). |
| AMBIGUOUS | Run a second participant. Single-N inconclusive. |
| DID_NOT_NOTICE | Bigger problem than honest-absence wording — the reasoning section is invisible. Rethink the visual hierarchy. |

---

## What this test does NOT validate

- Multi-user generalization (N=1)
- Mobile UX
- Operator (developer-perspective) UX
- Accessibility
- Performance under low bandwidth
- Cross-cultural / non-English comprehension
- Long-term retention
- Whether the user would PAY for the product

These remain unknowns after a single walkthrough and require separate observation efforts.

---

## Anti-patterns the facilitator must resist

1. **Explaining features the participant didn't find.** They didn't find them for a reason.
2. **Defending the design.** "Well, the reason we did that is..." — never.
3. **Skipping the comparison question** because it's uncomfortable.
4. **Interpreting behavior in the moment.** Record raw, analyze after.
5. **Drawing UI conclusions from a single user.** N=1 is a hypothesis, not a verdict.
6. **Treating "the user didn't notice X" as proof X doesn't matter.** It may mean the user didn't reach X yet.

---

## Activation note

This protocol is ready to execute the moment the three UI changes (CI workflow + PickModal confidence removal + honest-absence copy) ship to the environment a participant would see.

Until then: hold. Do not recruit. Recruit triggers when the pre-execution checklist above is fully green.
