// Phase 2B — Lessons Arth learned (manual seed for Report Card §6).
//
// These are the visible process updates Arth has made to his own
// thinking after losses or near-misses. Hand-authored for now;
// later they'll be produced by a backend retrospective job.

export interface ArthLesson {
  id: string;
  date: string;                  // YYYY-MM-DD
  trigger_summary: string;       // brief context (e.g. "After NVDA -2.1%")
  what_i_changed: string;        // first-person from Arth
  rule_change_summary: string;   // shorter abstract for list views
}

export const ARTH_LESSONS_SEED: ArthLesson[] = [
  {
    id: 'lesson-nvda-2026-05-20',
    date: '2026-05-20',
    trigger_summary: 'After NVDA -2.1% close (medium confidence call)',
    what_i_changed:
      "I now down-weight low-IV setups when earnings is less than six " +
      "weeks out. The IV being cheap is only an edge if the IV stays " +
      "where it was — and earnings cycles destroy that. From now on, " +
      "when I see an earnings event in the next six weeks, I'll flag it " +
      "explicitly before recommending the trade and bias toward " +
      "defined-risk structures with a lower delta.",
    rule_change_summary:
      'IV-based setups now flag earnings risk explicitly when event is <6w out.',
  },
  {
    id: 'lesson-tsla-2026-05-12',
    date: '2026-05-12',
    trigger_summary: 'After TSLA short stopped at +0.4% (correctly)',
    what_i_changed:
      "I held the invalidate line. Daily-close-above is the right stop " +
      "trigger for short setups — intraday wicks are too noisy and would " +
      "have stopped me out at -1.5% before the move came back. I'll " +
      "keep using daily-close-above as the canonical invalidate.",
    rule_change_summary:
      'Daily-close-above confirmed as the right stop trigger for short setups.',
  },
  {
    id: 'lesson-xle-2026-05-03',
    date: '2026-05-03',
    trigger_summary: 'After XLE early-exit on partial fill ambiguity',
    what_i_changed:
      "The user thought they were fully filled and exited early. They " +
      "weren't — only half the position was on. From now on, when a " +
      "paper trade has a partial-fill state, I'll show that explicitly " +
      "BEFORE recommending 'hold to target.' Confusion at the order " +
      "stage is a process bug, not a trade bug.",
    rule_change_summary:
      'Show partial-fill state before recommending hold-to-target.',
  },
  {
    id: 'lesson-meta-2026-04-22',
    date: '2026-04-22',
    trigger_summary: 'After MSFT skip turned into a +2.1% missed move',
    what_i_changed:
      "I noticed you skipped MSFT with 'too risky' as the reason, and " +
      "MSFT then ran +2.1%. The skip wasn't wrong — your risk filter " +
      "is your call — but I now show 'similar setups you skipped, how " +
      "they performed' so you can recalibrate your own filter against " +
      "data, not feeling. This is a feature to make your filter " +
      "tighter or looser based on its own track record.",
    rule_change_summary:
      'Surface "skipped-but-would-have-worked" calls on the Report Card.',
  },
];
