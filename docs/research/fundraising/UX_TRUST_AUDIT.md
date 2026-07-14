# ArthOS — Investor-Demo UX & Trust Audit

**Date:** 2026-06-20 · Reviewer hats: Stripe Head of Design / Sequoia design partner / ex-Apple HIG reviewer / fintech growth designer / investor-demo UX. **Audit only — no redesign, no new features.** Grounded in the actual product (every surface reviewed at desktop 1440 + mobile 391 this cycle, plus component code). Brutally honest; excellence called out where real; no invented problems.

## Headline

After this cycle's polish, **most of ArthOS is genuinely investor-grade.** The flagship surfaces (Bull vs Bear, Recommendation Trace, Track Record Integrity Card, Reflection Loop, Methodology + Workflow, Landing) are A/A+ — contained premium cards, consistent `rounded-xl`/hairline system, brand-accented hierarchy, honest copy. The remaining ROI is concentrated in **two real gaps** (loading states; a freshness-label honesty risk) and a handful of micro-polish items. Do not redesign anything — the product's problem is demand, not design.

## Per-page audit (7 questions)

### Landing / Onboarding — **A**
1. *Trust now:* honest promise ("nothing real at stake; we promise literacy"), 3-up trust strip. 2. *Reduces trust:* none. 3. *Unfinished:* none (fixed this cycle). 4. *Enterprise:* centered hero + trust strip reads premium. 5. *Amateur:* none. 6. *Investor nervous:* nothing. 7. *User leaves:* nothing.

### Discover — **A**
Clear masthead, real Buy top idea, Entry/Target/Exit, plain English. *Reduces trust:* the global ticker shows all indices at `+0.00%` when markets are closed — but it is **correctly labelled "Markets closed · delayed"**, so it reads honest, not broken (verified in code). *Investor nervous:* mild — repeated flat `0.00%` can still read static at a glance; the label largely disarms it (P2). Otherwise excellent.

### Today's Top Idea / Briefing — **A**
Hero card + honest "Cash is the call" empty-desk. Strong trust copy. No amateur tells.

### Bull vs Bear — **A+**
*Trust now:* both-sides framing + count pills + accented verdict; shows the case against its own call. *Unfinished/amateur:* none. *Flagship screenshot.* Nothing to fix.

### Recommendation Trace — **A**
Clean collapsible audit trail, grouped sections, plain adjustment labels, bold net-score footer. *User confusion:* the raw factor narratives (SMA/RSI/ATR) appear when expanded — acceptable because this is the explicit Layer-3 "audit trail," not the beginner default (P2 at most).

### Track Record Integrity Card — **A+ (one caveat)**
*Trust now:* contained card, hero stats, honesty footer ("win-rate hidden until 10 resolve"), freshness dot. *Investor nervous:* the freshness chip can read **"Fresh · Live" while the as-of date is several days old** (freshness is measured from last-write, not the equity date). A sharp diligence eye will challenge "fresh but as-of the 17th?" — see P0-A. The card design itself is excellent.

### Reflection Loop — **A**
Per-idea bordered cards, colored P/L pill, accented "What we learned." Premium. (Coverage is thin — a data matter, not UX.)

### Paper Portfolio — **A-**
*Trust now:* "Practice portfolio," honest breakdown, "source: live." *User confusion:* the "Where the P&L comes from" block is dense (three reconciliation rows) and renders neutral accounting deltas in **red**, which a beginner can misread as "everything's down/broken" (P2). Otherwise clean.

### Model Portfolios — **A-**
Clear thesis + track record + "Is this for me?". Minor wording ("flatters the past"); no visual issues.

### Methodology + Workflow — **A+**
Premium editorial + the numbered workflow timeline. Screenshot-worthy. Nothing to fix.

### Global Ticker — **B+ / acceptable**
Honest closed-market handling. Could feel more "alive" with a last-close framing, but not a credibility issue.

### Why Now — **A**
Accent card, concise, brand-consistent with the verdict block. Good.

## Cross-cutting finding (the biggest real one)

**No loading / skeleton states anywhere in v2** (`animate-pulse`/Skeleton: 0 matches across `apps/web/src/v2`). Data-driven cards render from `?? []`/undefined, so on first paint the Integrity Card, Reflection Loop, and idea metrics show `—`/`0`/empty and then **pop to real values** once data resolves. In a live demo on a cold load this looks like "is it working?" and undercuts the perceived-quality story exactly where it matters most (the trust/track-record surfaces). This is the single highest-ROI UX fix.

---

## Ranked findings

### P0 — damages trust or credibility
- **P0-A · Freshness label can read "Fresh" while data is stale.** Impact **8**, Effort **3**. *Investor:* high (diligence will catch it). *User:* low. *Files:* `apps/api/src/api/paper_canonical.py` (freshness source) + `apps/web/src/v2/components/TrackRecordIntegrityCard.tsx` (label copy). *Fix (copy/label only, no engine change):* show the as-of **date** next to "Live," or relabel the dot as "pipeline live" vs "data as of <date>." This is the one genuinely credibility-damaging item — and it's a label change, not a redesign.

### P1 — high-ROI improvements
- **P1-A · Add skeleton/loading states to the demo surfaces.** Impact **8**, Effort **4**. *Investor:* high (kills the "0 → real" flash in demos). *User:* med-high. *Files:* `TrackRecordIntegrityCard.tsx`, `ReflectionLoop.tsx`, `TrackRecord.tsx`, `PickPage.tsx` (render a card-shaped shimmer while `isLoading`/`!pid`). Reuse one tiny skeleton primitive; no new feature.
- **P1-B · Reserve card frames to prevent layout shift (CLS).** Impact **6**, Effort **3**. *Investor:* med. *User:* med. *Files:* same surfaces — render the bordered container immediately so content fills *into* it rather than appearing as loose "—". Pairs with P1-A.
- **P1-C · Number formatting consistency pass (tabular figures everywhere prices/P&L/% appear).** Impact **5**, Effort **2**. *Investor:* med (polish signal). *User:* low. *Files:* the metric tiles/rows across Integrity Card, Portfolio, Reflection. Verify `tabular-nums` on every numeric cell so columns don't jitter.

### P2 — nice-to-have polish
- **P2-A · Paper Portfolio "Where the P&L comes from": soften red for neutral deltas + reduce density.** Impact **4**, Effort **3**. *Files:* `PaperBook.tsx`.
- **P2-B · Ticker "alive" treatment** (last-close framing on closed days). Impact **3**, Effort **3**. *Files:* `GlobalTicker.tsx`.
- **P2-C · Model Portfolios wording** ("flatters the past" → "overstates past returns"). Impact **3**, Effort **1**. *Files:* `ModelPortfolioDetail.tsx`.
- **P2-D · Trace raw-narrative readability** (optional plain-language lead per row inside the audit trail). Impact **3**, Effort **4**. *Files:* `RecommendationTrace.tsx`. Low priority — the layer is meant to be technical.
- **P2-E · Empty-state premium-ness** on secondary "not yet connected" pages (keep out of demo regardless). Impact **2**, Effort **3**.

## What is already excellent (do NOT touch)

Bull vs Bear, Recommendation Trace, Integrity Card layout, Reflection Loop, Methodology + Workflow, Landing. Consistent component system (`rounded-xl` + `border-hairline` + brand-accent verdict blocks), honest copy discipline, plain-English beginner surfaces with Layer-3 detail gated behind toggles, gated metrics. This is a genuinely well-designed product; resist the urge to redesign for its own sake.

## Top 10 Highest-ROI UX Improvements

Sorted by **(Investor Impact × User Impact) ÷ Effort**. (User impact estimated 1–10 where not stated.)

| # | Improvement | Inv | User | Effort | Score | P |
|---|---|---|---|---|---|---|
| 1 | **Skeleton/loading states on demo surfaces** (P1-A) | 8 | 7 | 4 | **14.0** | P1 |
| 2 | **Reserve card frames to kill layout shift** (P1-B) | 6 | 6 | 3 | **12.0** | P1 |
| 3 | **Model Portfolios wording fix** (P2-C) | 3 | 4 | 1 | **12.0** | P2 |
| 4 | **Freshness: show as-of date / relabel live-vs-stale** (P0-A) | 8 | 4 | 3 | **10.7** | P0 |
| 5 | **Tabular-figures consistency pass** (P1-C) | 5 | 4 | 2 | **10.0** | P1 |
| 6 | **Paper Portfolio P&L block: soften red + density** (P2-A) | 4 | 5 | 3 | **6.7** | P2 |
| 7 | **Ticker last-close "alive" treatment** (P2-B) | 4 | 3 | 3 | **4.0** | P2 |
| 8 | **Spacing-rhythm sweep on idea detail** (consistency) | 3 | 3 | 3 | **3.0** | P2 |
| 9 | **Trace plain-language lead per row** (P2-D) | 3 | 4 | 4 | **3.0** | P2 |
| 10 | **Empty-state polish, secondary pages** (P2-E) | 2 | 3 | 3 | **2.0** | P2 |

*(Score = Inv × User ÷ Effort. #3 ranks high purely because it's near-zero effort.)*

## Bottom line for the 30-day funding window

There is **one** thing worth touching before a funding meeting: **add loading/skeleton states (and reserve the card frames)** so the trust surfaces never flash empty in a live demo (Top-10 #1 + #2). Optionally make the **freshness label honest about the data date** (#4) — the only genuinely credibility-adjacent item, and a copy change. Everything else is P2 polish that will not move a single investor. The design is not the bottleneck; resist redesigning a product that already looks like it raised a Series A. Spend the 30 days on demand, not pixels.
