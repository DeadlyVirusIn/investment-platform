# UX-11 Round 1 Prompt — Independent Position

You are participating in a 4-way adversarial design debate.

## Read first
Read the shared brief: `docs/research/debates/UX_11_interactive/BRIEF.md` (relative to repo root `C:/Users/kunal/projects/investment-platform`).

## Important context
This debate sits ON TOP of the locked UX-10 Conviction Engine. The master at `docs/research/UX_10_CONVICTION_ENGINE.md` is the parent spec. UX-11 must respect every UX-10 invariant. **Do not propose changes to UX-10 locks** — propose UX-11 additions/replacements that work alongside them.

## Task
Write your **independent Round 1 position** as a single markdown file. Cover all 11 questions in the brief. Word target: **2,000–3,000 words total**.

## Mindset
- This is **adversarial**. Take strong positions. No fence-sitting.
- Defend your weakest claim preemptively.
- The user explicitly noted UX-10 felt "static," "research-terminal-like," "analyst-cards." Your job is to design the LIVE / INTERACTIVE / EMOTIONALLY-GUIDED layer — without violating UX-10's anti-casino, anti-spam, anti-AI-theater locks.

## Format (strict)

```
# Model: <your name>
## Round: 1

## Position summary (300 words max)

## Q1. ConvictionTile shape
[concrete spec — fields, dims, visual, click target]

## Q2. AIReadHero
[copy length, voice rules, examples — 3 good + 3 bad]

## Q3. ReasoningDrawer experience
[sections, motion timing, dismiss behavior, mobile]

## Q4. AI voice rules
[composer transformation rules, banned phrases, tone calibration]

## Q5. Visual hierarchy ramp
[4 layers — concrete surface treatment per layer]

## Q6. Subtle background depth
[what survives the UX-10 anti-gradient lock]

## Q7. Tile click → drawer interaction
[step-by-step UX, motion budget, accessibility]

## Q8. Secondary surfaces structure
[layout below tiles — what shows, what doesn't, what order]

## Q9. Mobile experience
[< 720px breakpoint behavior]

## Q10. Biggest failure modes
[your top 3]

## Q11. Final synthesis
[your top 5 master locks]
```

## Hard rules
- Cite specifics: tile dimensions, motion ms, copy strings, color values, easing functions.
- No fluff sections, no "in conclusion."
- Identify your model name in the header.

## Output
Output the full markdown response directly to stdout. Do NOT write files. Do NOT call tools.
