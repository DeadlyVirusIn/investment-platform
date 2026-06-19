# ArthOS — Innovation Fund Audit (2026-06-19)

Evaluation only. No features built. Branch `mvp/ideas-you-can-follow`.

## 1. Product positioning

### The problem
First-time investors hit a wall: they don't know **what to buy, why, when to
sell, or how to learn** — and every existing tool fails them in a specific way:
- **Robinhood / brokerages** — optimise for *trading volume* (gamified, real
  money, PFOF). They hand a beginner a loaded gun, not an education.
- **Seeking Alpha** — opinion articles behind a paywall; no structured plan, no
  honest scorecard, conflicting takes.
- **Yahoo Finance** — a data firehose; quotes and headlines, no guidance.
- **TradingView** — charts + indicators for traders; assumes you already know
  ATR, RSI, support/resistance. Useless to a true beginner.
- **Generic AI stock pickers** — a black box: "Buy NVDA." No reasoning you can
  check, no track record, no learning, often fabricated targets.

### What ArthOS is
**"Ideas you can follow and prove."** A beginner-first AI investing copilot that
turns every recommendation into a **complete, plain-English investment idea**
— thesis, a concrete plan (Entry / Target / Exit-if-wrong / Timeframe), why it
exists, the key risk, recent news — that you can **practice with paper money**
and **prove over time**, while it **teaches you to think like an investor**
(a guided Day-N path: Discover → Learn → Practice → Build → Automate → Invest).

### Differentiation (the wedge)
| vs | Their model | ArthOS difference |
|---|---|---|
| Robinhood | Real-money trading, gamified | Practice money, zero stakes, literacy-first; no dopamine loop |
| Seeking Alpha | Opinion articles | Structured plain-English idea + explicit plan + honest track record |
| Yahoo Finance | Data terminal | One reasoned idea at a time, not a firehose |
| TradingView | Trader charts + indicators | Beginner plans; jargon (ATR/RSI/DTE/IV/Greeks) removed by design |
| AI pickers | Black-box "Buy X" | Shows the working (why/risks/evidence), never fabricates numbers, proves in paper, and teaches |

### Strongest unique value proposition
> **The only AI investing copilot that turns each pick into a complete,
> plain-English idea you can practice and prove — and learn from — before any
> real money is at risk.**

Three things competitors don't combine: **(1) plain-English completeness**
(every idea is a full plan, no jargon), **(2) prove-it honesty** (practice-first,
real per-user track record, no fabricated targets, honest empty states), and
**(3) it teaches** (a progression spine, not a tip feed).

## 2. Honesty as a moat
ArthOS's hardest-to-copy asset is its **honest-data discipline**, enforced
throughout:
- Never fabricates numbers — fundamentals/news show real data or honest
  placeholders; plans are derived from real price + volatility (labelled
  "paper planning estimate, not advice").
- Per-user practice books (no shared/demo confusion) — your track record is
  *yours*.
- Confidence is explained, not asserted ("how strongly the model supports this
  … not a guarantee").
- Jargon is removed on beginner surfaces (verified: 0 leaked terms) and only
  retained on explicitly-advanced, gated pages.
This is a positioning a "move-fast" competitor structurally avoids — and it is
exactly what an innovation fund + a regulator-aware beta wants to see.

## 3. Demo readiness — the strongest screens
Ranked for a fund demo:
1. **Discover → Today's Top Idea** — a real company (name + ticker + sector),
   plain confidence, and a full plan (Entry/Target/Exit/Timeframe) above the
   fold. The "wow, a beginner actually understands this" moment.
2. **Idea detail (Pick page)** — What to do next, why it exists, key risks,
   holding period, recent news, honest fundamentals placeholder.
3. **Model Portfolio detail** — Identity (who/why/how-long), Education
   (diversification/concentration/volatility/rebalancing), Trust (how picked /
   how often changes / what success looks like / what could go wrong),
   one-tap Follow.
4. **My Portfolio (Paper Book)** — "being prepared" honest state → real
   positions with live marks.
5. **Progress spine** — Discover→Learn→Practice→Build→Automate→Invest.
6. **Options Practice** — advanced, behind a disclosure, jargon translated
   ("Time left / Risk level / Maximum loss / What would make it fail").
7. **Landing** — value prop + the promise ("we promise literacy, not returns").

See `DEMO_SCRIPT.md` for the 5- and 15-minute flows.

## 4. Gaps an investor will probe (be ready)
- **Data depth** — fundamentals/news are sparse for many names (honest
  placeholders); plans are ATR-derived heuristics, not an engine target model.
- **Options single-stock universe** — blocked on quote quality (Tradier prod
  liquidity gate); validated Monday. ETFs work today.
- **No real-money path** — intentional ceiling; "Automate" and "Invest" are
  roadmap. Frame as deliberate (literacy before stakes), not missing.
- **Identity is a device id** — fine for invite beta; real IdP before public.

## 5. The one-liner for the pitch
> "Robinhood taught a generation to *trade*. ArthOS teaches them to *invest* —
> one plain-English idea a day, practised with fake money and proven over time,
> until they actually understand what they own."
