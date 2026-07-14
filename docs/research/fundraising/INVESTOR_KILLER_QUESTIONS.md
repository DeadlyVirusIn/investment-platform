# ArthOS — The 10 Credibility-Killer Questions (and evidence-backed answers)

**Date:** 2026-06-20 · Final investor-prep exercise. After 10 minutes in the product, what would a Sequoia partner / fintech exec / broker-dealer exec / innovation-fund reviewer ask that could *damage credibility* — and how do we answer using **evidence already in the product**? Each answer flags honestly: **[STRONG]** answerable with in-product evidence · **[PARTIAL]** evidence + a disclosure · **[CONCEDE]** no product evidence — concede and reframe, don't bluff.

The single most useful output of this exercise: knowing which questions you can win on evidence vs which you must concede gracefully. Bluffing a CONCEDE question is how you lose the room.

---

### 1. "Are these numbers real, or staged for the demo?" — *(all reviewers)* **[STRONG]**
Why dangerous: if the track record looks fabricated, the whole trust thesis collapses. Evidence in product: every figure reproduces from source — NAV, +5.21%, $5,951 realized, 30 open, 63 closed all trace to DB rows; recommendations are keyed by `snapshot_hash` and regenerable; the Integrity Card **refuses to publish a win-rate until 10 ideas resolve** (you can see "Hidden" on a fresh book). Answer: "Every number is computed from real paper trades and live snapshots — here's the audit trail, and we gate metrics we can't back. We ran a full internal correctness certification; happy to walk the source queries." Disclose proactively: the demo book is a *seeded clone* of a long-running paper account — real engine outcomes, openly labelled.

### 2. "Your win-rate is ~50%. Where's the edge?" — *(Sequoia / quant)* **[PARTIAL → reframe]**
Why dangerous: invites "so your AI is a coin flip." Evidence: the product *deliberately* sells judgment and trust, not alpha — the Bull/Bear card shows the case against every idea; nothing claims to beat the market. Answer: "We don't sell edge — an honest 50% shown openly is the point; a literacy/trust product that cherry-picked 80% would be the red flag. If edge emerges it's upside the thesis doesn't depend on." Concede the implied ask (we are not an alpha shop) rather than overclaim.

### 3. "It says 'as of Jun 17' but today is Jun 20 — is this even live?" — *(fintech exec / broker-dealer)* **[STRONG, post-fix]**
Why dangerous: stale data behind a "live/fresh" badge reads as fake or broken. Evidence: the Integrity Card now shows the real **as-of date** and an **amber** indicator when data is older (it no longer claims "Fresh"); the API independently reports `degraded`. Answer: "We surface data age honestly — that amber 'as of Jun 17' is the product telling the truth, not hiding it. In the dev environment the pipeline hasn't run today; on a live cadence it's current." The honesty *is* the answer.

### 4. "Is your AI giving financial advice? What's your regulatory exposure?" — *(broker-dealer / fintech exec)* **[STRONG]**
Why dangerous: "unlicensed advice" can end the meeting. Evidence: **paper-only by construction** — there is no live-execution path in the product, "practice money, nothing real at risk" is on the portfolio, "not investment advice" disclaimers are on the idea pages, and every idea shows its downside. Answer: "We're architected *outside* advisor/broker territory — education-framed, paper-only, no execution, no order flow. The safety is structural, not a policy promise." This is one of the strongest answers in the product.

### 5. "Your win-rate counts 62 trades across 46 ideas — fills or ideas?" — *(sharp quant / DD analyst)* **[PARTIAL]**
Why dangerous: looks like metric inflation if caught un-disclosed. Evidence: the label says "resolved trades," and the internal certification documents it (62 sell-fills, 46 distinct ideas; scale-outs count separately). Answer: "Per resolved trade today — we label it that way deliberately; a per-idea view is a known item. We disclose the definition rather than bury it." Win by having already named it.

### 6. "You show 63 closed but only 2 reflections — why the gap?" — *(detail-oriented reviewer)* **[PARTIAL]**
Why dangerous: looks like the flagship "self-grading" feature barely works. Evidence: 2 of 63 closes retain `opened_by_recommendation_id` (older closes came from replay/execution before per-idea attribution existed); every reflection shown is real, none fabricated. Answer: "Reflections only appear where we can honestly tie a closed position back to the originating call — coverage grows as new attributed ideas close. We'd rather show 2 real than 63 invented." Honesty reframes a gap as discipline.

### 7. "Can one user see another's data? Is this actually scoped?" — *(security-minded exec)* **[STRONG]**
Why dangerous: a leak is fatal for a finance product. Evidence: per-device resolver (`user:<device>:stock`), the web client always sends the device header, the canonical endpoint filters `portfolio_id` + `source='live'`, and the executed-data hooks are `enabled:!!pid`-guarded (we *found and fixed* an unscoped-fetch flash in our own DD pass). A cold device gets an empty book (guardrail test). Answer: "Scoped per user by construction; we caught and closed the one place a global aggregate could flash, and have a regression test." Showing you found your own bug builds credibility.

### 8. "Anyone can wrap GPT. What's actually defensible here?" — *(Sequoia)* **[PARTIAL → concede the timeline]**
Why dangerous: "thin GPT wrapper" is a pass. Evidence: the numbers are **not** LLM-generated — a deterministic engine produces reproducible evidence (`snapshot_hash`); Bull/Bear and the audit trail are derived from *stored* evidence, not free text; the self-grading loop runs on real outcomes. Answer: "The hard part isn't an opinion — it's accountability and a per-user track record that compounds. A wrapper can copy a screen, not a year of audited proof." Concede honestly: that moat is real in design but **unproven until we have scale** — see Q9.

### 9. "Where are your users? Show me retention." — *(every serious investor; the killer)* **[CONCEDE]**
Why dangerous: this is the real question, and the product has **no answer** — no users, no retention curve. Do **not** bluff. Answer: "We don't have it yet, and I won't pretend otherwise. What we have is the rare thing at pre-seed — a working, audited product — which de-risks execution. The next 30–60 days are entirely about proving weekly pull; that's exactly what this round funds, and it's the milestone I'd want you to hold me to." Conceding this with a plan is more credible than any deflection.

### 10. "How do you make money without order flow or ads — and is 'literacy' even monetizable?" — *(fintech exec / innovation reviewer)* **[CONCEDE + reframe]**
Why dangerous: education has a brutal monetization history. Evidence in product: no PFOF, no ads, no engagement dark patterns — by construction (trust is the product). Answer: "Model is freemium → subscription, then B2B/B2B2C literacy — and I'll be honest that monetization and the education-retention problem are unproven; they're the risk. We're not asking you to believe the revenue line yet; we're asking you to back the wedge and the team while we prove pull." Naming the category's graveyard before they do disarms it.

---

## The honest scorecard

- **Win on evidence (5):** #1 real numbers, #3 freshness honesty, #4 regulatory/paper-only, #7 scoping/isolation, and the *design* of #8 defensibility. These are genuinely strong — the product backs them.
- **Win with a disclosure (3):** #2 no-edge (reframe), #5 win-rate definition, #6 reflection coverage. Already named internally — name them first in the room.
- **Cannot answer — concede (2):** #9 traction/retention and #10 monetization. The product cannot help here. Conceding both, with the 30-day demand plan, is the credible play; bluffing either loses the meeting.

## The one-line prep

Lead the demo with the five you win on (numbers are real, honest about data age, paper-safe, properly scoped, not a wrapper), pre-empt the three disclosures before they're asked, and when the traction/monetization questions come — and they will — **concede cleanly and point to the demand-validation plan.** Credibility comes from the questions you answer with evidence *and* the two you're honest enough not to fake.
