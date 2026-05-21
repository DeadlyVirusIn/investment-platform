# Creative Direction — Editorial Authority + Voice System

**Status**: accepted 2026-05-15
**Phase**: K (Creative Direction)
**Inherits**: `CREATIVE_DIRECTION_SPINE.md`

---

## Anonymous institutional voice

The product has no AI character. No name. No sigil. No "Desk" attribution mark. The strategist is the *editorial voice* of the product itself, in first-person plural, with no visible byline.

The AI's presence is carried through:

- Voice consistency
- Editorial intelligence in copy
- Typographic precision
- Material atmosphere

Not through:

- Names ("Atlas," "Tide," etc.) — rejected
- Smallcaps attribution marks ("THE DESK") — rejected
- AI sigils, robot icons, sparkle marks — rejected
- "Powered by AI" stamps — rejected
- Assistant-product branding patterns — rejected

## Naming layers (three layers, distinct)

| layer | name | purpose |
|---|---|---|
| Product name | (existing) | The app the user signs into |
| Edition name | **Today's Briefing** | The thing the user reads today |
| Voice attribution | none (pure editorial *we*) | Who's speaking when AI speaks |

The product name is unchanged. The edition name is locked. The voice attribution is *absent by design* — anonymous editorial authority.

## Edition name commitment

**Today's Briefing.** Always set with the date underneath. Optional edition number for editorial-grade weight.

### Masthead format (signature visual moment)

```
Today's Briefing
Friday, May 15 · Edition #142
```

- Title line: Newsreader at editorial scale (~clamp 36-56px)
- Date + edition line: Inter at 13-14px, `--ink-muted`, letter-spacing 0.04em
- This is the *only* place "Today's Briefing" appears at hero scale
- Everywhere else, refer obliquely ("today's note", "this edition")

### Masthead composition rules (locked)

1. Lives only on `/options/overview` (Today). Other surfaces have section headers, not mastheads.
2. First thing in the viewport. Above any orientation. Above everything.
3. Always three lines, never more, never fewer.
4. Type only. No icons. No gradients. No drop shadow.
5. No background container. Set directly on the page background.
6. Optional single 1px hairline beneath if visual designer decides it's needed for separation. Default: no rule. Whitespace separates.

## Voice mode — pure editorial *we*

**Single voice mode.** No inflection marks. No "Desk" attribution. The voice is first-person plural, used everywhere by default.

Example:

> *"We're watching twenty-five setups across five underlyings. Premium environment is still loading."*

No visible byline. The voice IS the page.

### Voice rules (locked)

1. **No "AI" mentions in user-facing copy.** Never write "the AI thinks", "our system found", "the model predicts". Always: "we think", "we found", "we surface".
2. **No "system" / "engine" mentions.** Never write "the engine generated", "the system flagged".
3. **First-person plural always.** Never "I". Never "you should". Always "we".
4. **No exclamations.** Never. Period.
5. **No questions to the user except in "ask back" responses.** No "Want to learn more?" prompts. The user asks; we don't ask back.
6. **No hedging language.** "Maybe," "perhaps," "it seems" are banned. If we're not sure, we say "we're not sure" or "we'd wait."
7. **Inflection through brevity, not punctuation.** No em-dash flair, no ellipses, no italics-for-emphasis-only. The sentence itself carries the inflection.
8. **No second-person prescriptions.** Don't say "You should manage this position." Say "We'd manage this position by..." Position the AI as advising itself; the user observes that advice.

## Engine-vocabulary firewall

The load-bearing rule from the spine, reinforced with concrete examples.

| ❌ engine word | ✅ editorial replacement |
|---|---|
| `composite_confidence` | "fit with today's market" / "today's read on this" |
| `would_trade_count` | "setups we'd consider" / "what we're watching" |
| `shadow run` | "today's review" / "this morning's pass" |
| `rule_id` | (never visible) — render strategy name in human casing |
| `promotion_gate` | (never visible) — replace with "until we've seen more" |
| `thresholds_met` | "we're confident enough" / "we've seen this hold" |
| `triggering_rule` | (never visible) — drawer footer redesign required |
| `iv_universe_mean` | "premium environment" |
| `evaluated_today` | (never visible — internal telemetry only) |
| `underlying` | "ticker" / "symbol" / "position" depending on context |
| `posture` | "we're observing" / "we're calibrated" — engine state becomes a verb the user reads |

**Enforcement mechanic** (proposed for implementation phase): CI lint rule scans `apps/web/src/**/*.tsx` for left-column tokens. Fails CI if found in user-facing strings.

## The ask-back gesture — under anonymous authority

The signature interaction. Anonymous-authority framing.

### Visual treatment

- After reading any qualifying section, user sees a single quiet line:

  *"Ask one thing back."*

  Set in Newsreader italic, 14-15px, `--ink-muted`. Below the section. Never inside a card. Never a button.

- Clicking opens a single inline input at the same width as the section. No floating chat panel. No drawer. Inline.

- User types one question (max ~120 chars enforced). Hits Enter.

- Page composes a response inline, beneath the input, in the same voice as the briefing. Response replaces the input field; the question becomes a quoted line above the response.

- No "ask another." No thread. No history sidebar. Ephemeral, scoped to this session.

### Ask-back rarity rules (locked)

Appears on:

- Tier 1 (lead) setup in each lane in Opportunities
- Today's strongest read (conviction field)
- Decisive Holdings positions (`stop_loss`, `take_profit`)
- Per-symbol Research deep page (once, at end)
- Per-approach deep page (once, at end)

Does not appear on:

- Tier 2 or Tier 3 setups in any lane
- Tier 2 setups in Today
- `hold` / `expiring` / `roll` / `catalyst_caution` Holdings positions
- Journal entries
- Learn (playbook) pages
- Approaches library page (only deep pages)
- Empty states

**Viewport rule**: never more than one ask-back affordance inside the same visual viewport (~one screen height at typical reading zoom).

### Why ephemeral

Persistent ask history would re-introduce dashboard energy ("manage your conversations"). The product is a briefing, not a chat log. The follow-up dies with the session.

## Voice tonal range (so the voice doesn't read monotone)

Anonymous editorial authority is one voice. A single voice has tonal range. Lock the range:

| tone | when used | example |
|---|---|---|
| Calm baseline | Quiet days, neutral observations | *"We're watching twenty-five setups."* |
| Quiet conviction | Something we believe in | *"This is the strongest setup we've seen this week."* |
| Honest restraint | Data gaps, uncertain regime | *"We don't classify regime fit on incomplete data."* |
| Decisive directive | Stop-loss, take-profit, expiring | *"Take the loss. The thesis is broken."* |
| Observational restraint | Empty days | *"Nothing's worth your time today. We'll meet you tomorrow."* |

### Forbidden tones

- Excited / celebratory ("Great news!")
- Apologetic ("Sorry, we couldn't…")
- Cautious-bureaucratic ("Please note that…")
- Pedagogical-condescending ("Remember, options can lose money…")
- Cheerleading ("You've got this!")
- Hedge-fund-bro ("We're crushing it.")

## Editorial transition language

Used for connecting tiers within a section (e.g., the editorial sentence that bridges Tier 1 setup to Tier 2 setups in an Opportunities lane).

### Anti-template rule (locked)

Transition language must NEVER become formulaic. If every lane repeats *"Three more we'd take alongside it."* the voice begins feeling procedurally lyrical.

Required variability:

- Phrasing variability across lanes and days
- Contextual tone shifts (decisive day vs quiet day)
- Occasional omission (some lanes have no transition)
- Asymmetric transition structure (sometimes 1 transition, sometimes 2, sometimes 0)
- Transition can be question-shaped, statement-shaped, or contextual-aside-shaped

The voice must feel **editorially authored, not algorithmically poetic**.

A catalog of transitions and their generative rules is deferred to the implementation-phase **Voice + Editorial Cadence** sub-artifact, but the anti-template rule is locked now.

## Where the editorial voice lives (and doesn't)

| surface | masthead | ask-back | tonal range used |
|---|---|---|---|
| Today | yes | yes, after qualifying section | full range |
| Opportunities | no — section header only | yes, lead setup only per lane | calm + conviction + restraint |
| Holdings | no | yes, decisive guidance only | full range, especially decisive directive |
| Research (per-symbol) | no | yes, once at end | calm + conviction |
| Approaches (deep) | no | yes, once at end | calm + restraint |
| Journal | no — entries quote past notes | no | observational |
| Learn (Playbooks) | no | no — Learn is reference, not briefing | pedagogical but not condescending |

## What this artifact commits us to NOT building

- Chat window
- Conversation history
- "Talk to your AI" tab
- Persistent thread per user
- Prompt suggestions / "try asking" hints
- AI sidebar
- "Ask Atlas" / named-character moment
- Robot icons, sparkle icons, AI badges, "Powered by AI" notes
- "Model output" / "transparency dashboard" surface
- Anything visually communicating "this is an AI chatbot"

## Assets committed by this artifact

| asset | commitment |
|---|---|
| Edition name | "Today's Briefing" |
| Voice attribution | Pure first-person plural editorial *we* |
| Strategist character | None — anonymous authority |
| Ask-back gesture | Inline, single-question, ephemeral, viewport-limited |
| Engine-vocab firewall | Hard rule; CI lint candidate |
| Masthead | Newsreader title + Inter date + edition number; type-only; one viewport position (Today) |
| Tonal range | 5 tones locked; 6 forbidden tones locked |
| Transition language | Anti-template rule locked; catalog deferred |

## Linked artifacts

- `CREATIVE_DIRECTION_SPINE.md`
- `CREATIVE_DIRECTION_CHROME.md`
- `CREATIVE_DIRECTION_STUDIES.md`
- `CREATIVE_DIRECTION_COLOR_MATERIAL.md`
