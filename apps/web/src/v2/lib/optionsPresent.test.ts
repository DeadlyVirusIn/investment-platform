// optionsPresent — unit coverage. Pure functions, no I/O, no DOM.
// Anchored on real engine vocabulary (rule_ids, tiers, bias) so the
// trader-facing translation stays honest and never leaks raw ids.

import { describe, it, expect } from 'vitest';
import {
  strategyName,
  strategyTone,
  strategyDescriptor,
  confidencePct,
  confidenceLabel,
  premiumLabel,
  liquidityLabel,
  catalystLabel,
  thesisLine,
  whyPoints,
  presentOption,
  rankSetups,
  topSetup,
  humanizeAge,
  quoteFreshness,
  formatRunDate,
  engineView,
  rejectedList,
  presentEconomics,
  formatPricedAsOf,
  actionDirective,
  presentLegs,
} from './optionsPresent';
import type { OptionsOpportunity } from './optionsLanes';

function mk(p: Partial<OptionsOpportunity> = {}): OptionsOpportunity {
  return {
    observation_id: 1,
    underlying: 'QQQ',
    rule_id: 'SHORT_PUT_CREDIT_SPREAD',
    family: 'engine_executable',
    engine_compatible: true,
    above_floor: false,
    bias: 'bullish',
    directional_view: 'Profits if the underlying holds above the short put.',
    composite_score: 0.62,
    dte: 16,
    expiry: '2026-06-18',
    strike: 720,
    option_type: 'put',
    risk_profile: 'defined',
    premium_tier: 'average',
    liquidity_tier: 'good',
    ...p,
  };
}

describe('strategyName', () => {
  it('maps known v1 structures to human names', () => {
    expect(strategyName('SHORT_PUT_CREDIT_SPREAD')).toBe('Put Credit Spread');
    expect(strategyName('SHORT_CALL_CREDIT_SPREAD')).toBe('Call Credit Spread');
    expect(strategyName('IRON_CONDOR')).toBe('Iron Condor');
    expect(strategyName('LONG_CALL')).toBe('Long Call');
  });
  it('title-cases unknown rule_ids — never returns the raw id', () => {
    expect(strategyName('SOME_NEW_STRUCTURE')).toBe('Some New Structure');
    expect(strategyName('SOME_NEW_STRUCTURE')).not.toContain('_');
  });
});

describe('strategyTone', () => {
  it('derives tone from known meta', () => {
    expect(strategyTone('SHORT_PUT_CREDIT_SPREAD')).toBe('bull');
    expect(strategyTone('SHORT_CALL_CREDIT_SPREAD')).toBe('bear');
    expect(strategyTone('IRON_CONDOR')).toBe('neutral');
    expect(strategyTone('LONG_STRADDLE')).toBe('vol');
  });
  it('falls back to the bias word for unknown ids', () => {
    expect(strategyTone('MYSTERY', 'bearish')).toBe('bear');
    expect(strategyTone('MYSTERY', 'neutral')).toBe('neutral');
  });
});

describe('strategyDescriptor', () => {
  it('income structures read as "<bias> income · defined risk"', () => {
    expect(strategyDescriptor('SHORT_PUT_CREDIT_SPREAD', 'bullish', 'defined'))
      .toBe('Bullish income · defined risk');
    expect(strategyDescriptor('IRON_CONDOR', 'neutral', 'defined'))
      .toBe('Neutral income · defined risk');
  });
  it('directional structures read as "<bias> directional"', () => {
    expect(strategyDescriptor('LONG_CALL', 'bullish', 'defined'))
      .toBe('Bullish directional');
  });
  it('vol structures read as volatility premium', () => {
    expect(strategyDescriptor('LONG_STRADDLE', 'neutral', 'defined'))
      .toBe('Volatility · long premium');
  });
});

describe('confidence', () => {
  it('scales composite 0–1 to 0–100', () => {
    expect(confidencePct(0.81)).toBe(81);
    expect(confidencePct(0.624)).toBe(62);
    expect(confidencePct(0)).toBe(0);
  });
  it('guards non-finite input', () => {
    expect(confidencePct(NaN)).toBe(0);
  });
  it('labels by band', () => {
    expect(confidenceLabel(81)).toBe('High');
    expect(confidenceLabel(62)).toBe('Medium');
    expect(confidenceLabel(40)).toBe('Low');
  });
});

describe('tier labels', () => {
  it('formats known premium tiers, null otherwise', () => {
    expect(premiumLabel('rich')).toBe('Rich premium');
    expect(premiumLabel('average')).toBe('Average premium');
    expect(premiumLabel('unknown')).toBeNull();
    expect(premiumLabel(null)).toBeNull();
  });
  it('formats known liquidity tiers, null otherwise', () => {
    expect(liquidityLabel('good')).toBe('Good liquidity');
    expect(liquidityLabel('poor')).toBe('Poor liquidity');
    expect(liquidityLabel(undefined)).toBeNull();
  });
});

describe('catalystLabel', () => {
  it('renders "<Event> in N days"', () => {
    expect(catalystLabel('earnings', 9)).toBe('Earnings in 9 days');
    expect(catalystLabel('earnings', 1)).toBe('Earnings in 1 day');
  });
  it('renders "<Event> today" at zero/negative', () => {
    expect(catalystLabel('earnings', 0)).toBe('Earnings today');
  });
  it('returns null when no event', () => {
    expect(catalystLabel(null, 5)).toBeNull();
    expect(catalystLabel(undefined, undefined)).toBeNull();
  });
});

describe('thesisLine + whyPoints', () => {
  it('prefers directional_view for the thesis', () => {
    expect(thesisLine(mk())).toBe(
      'Profits if the underlying holds above the short put.',
    );
  });
  it('prefers rationale_points for the bullets, capped', () => {
    const o = mk({ rationale_points: ['A', 'B', 'C', 'D', 'E'] });
    expect(whyPoints(o)).toEqual(['A', 'B', 'C', 'D']);
  });
  it('falls back to fit reasons when no rationale_points', () => {
    const o = mk({
      rationale_points: null,
      strategy_fit_reason: 'fit',
      iv_fit_reason: 'iv',
      dte_fit_reason: null,
      liquidity_fit_reason: 'liq',
    });
    expect(whyPoints(o)).toEqual(['fit', 'iv', 'liq']);
  });
  it('de-dupes bullets', () => {
    const o = mk({ rationale_points: ['same', 'same', 'diff'] });
    expect(whyPoints(o)).toEqual(['same', 'diff']);
  });
});

describe('presentOption', () => {
  it('produces a full trader view model with no raw rule_id', () => {
    const v = presentOption(mk({ composite_score: 0.81, above_floor: true }));
    expect(v.strategyName).toBe('Put Credit Spread');
    expect(v.descriptor).toBe('Bullish income · defined risk');
    expect(v.confidence).toBe(81);
    expect(v.confidenceLabel).toBe('High');
    expect(v.dte).toBe(16);
    expect(v.premiumLabel).toBe('Average premium');
    expect(v.liquidityLabel).toBe('Good liquidity');
    expect(v.qualified).toBe(true);
  });
});

describe('rankSetups / topSetup', () => {
  it('puts qualified ahead of unqualified, then by confidence', () => {
    const items = [
      mk({ observation_id: 1, composite_score: 0.9, above_floor: false }),
      mk({ observation_id: 2, composite_score: 0.5, above_floor: true }),
      mk({ observation_id: 3, composite_score: 0.7, above_floor: false }),
    ];
    const ranked = rankSetups(items);
    expect(ranked.map((r) => r.observationId)).toEqual([2, 1, 3]);
    expect(topSetup(items)?.observationId).toBe(2);
  });
  it('returns null top for empty list', () => {
    expect(topSetup([])).toBeNull();
  });
});

describe('humanizeAge', () => {
  it('humanizes seconds into m/h/d, null when unknown', () => {
    expect(humanizeAge(30)).toBe('just now');
    expect(humanizeAge(600)).toBe('10m old');
    expect(humanizeAge(7200)).toBe('2h old');
    expect(humanizeAge(172800)).toBe('2d old');
    expect(humanizeAge(null)).toBeNull();
    expect(humanizeAge(-5)).toBeNull();
  });
});

describe('quoteFreshness', () => {
  it('Fresh under 24h, Stale over, Unknown when null', () => {
    expect(quoteFreshness(600)).toEqual({ label: 'Fresh', stale: false });
    expect(quoteFreshness(90000)).toEqual({ label: 'Stale', stale: true });
    expect(quoteFreshness(null)).toEqual({ label: 'Unknown', stale: true });
  });
});

describe('formatRunDate', () => {
  it('formats ISO date as MMM D, YYYY', () => {
    expect(formatRunDate('2026-06-01')).toBe('Jun 1, 2026');
    expect(formatRunDate('2026-06-18T13:00:00Z')).toBe('Jun 18, 2026');
  });
  it('null on missing/invalid', () => {
    expect(formatRunDate(null)).toBeNull();
    expect(formatRunDate('nope')).toBeNull();
  });
});

describe('engineView', () => {
  it('maps ranking_breakdown to trader labels and 0–100 values', () => {
    const rows = engineView({ score: 0.4, freshness: 0.2, liquidity: 0.15, iv_fit: 0.15, event: 0.1 });
    expect(rows).toEqual([
      { key: 'score', label: 'Strategy fit', value: 40 },
      { key: 'freshness', label: 'Signal freshness', value: 20 },
      { key: 'liquidity', label: 'Liquidity', value: 15 },
      { key: 'iv_fit', label: 'IV fit', value: 15 },
      { key: 'event', label: 'Catalyst weight', value: 10 },
    ]);
  });
  it('skips missing components, empty when absent', () => {
    expect(engineView({ score: 0.5 })).toEqual([{ key: 'score', label: 'Strategy fit', value: 50 }]);
    expect(engineView(null)).toEqual([]);
  });
});

describe('rejectedList', () => {
  it('maps rule_id to strategy name + reason, never raw id', () => {
    const out = rejectedList([{ rule_id: 'BULL_PUT_SPREAD', reason: 'credit too thin at current IV' }]);
    expect(out).toEqual([{ name: 'Bull Put Spread', reason: 'credit too thin at current IV' }]);
    expect(out[0].name).not.toContain('_');
  });
  it('drops entries with empty reason; empty when absent', () => {
    expect(rejectedList([{ rule_id: 'LONG_CALL', reason: '' }])).toEqual([]);
    expect(rejectedList(null)).toEqual([]);
  });
});

describe('presentOption B.1 fields', () => {
  it('surfaces freshness, as-of, engine view, rejected', () => {
    const v = presentOption(mk({
      run_date: '2026-06-01',
      quote_age_seconds: 7200,
      ranking_breakdown: { score: 0.6, freshness: 0.2, liquidity: 0.15, iv_fit: 0.15, event: 0.1 },
      rejected_alternatives: [{ rule_id: 'BULL_PUT_SPREAD', reason: 'thin credit' }],
    }));
    expect(v.runDate).toBe('Jun 1, 2026');
    expect(v.quoteAge).toBe('2h old');
    expect(v.freshness).toEqual({ label: 'Fresh', stale: false });
    expect(v.engine[0]).toEqual({ key: 'score', label: 'Strategy fit', value: 60 });
    expect(v.rejected).toEqual([{ name: 'Bull Put Spread', reason: 'thin credit' }]);
  });
});

describe('formatPricedAsOf', () => {
  it('formats ISO datetime as "Mon D, HH:MM"', () => {
    expect(formatPricedAsOf('2026-06-02T14:15:10Z')).toBe('Jun 2, 14:15');
    expect(formatPricedAsOf('2026-06-02 09:05:00')).toBe('Jun 2, 09:05');
  });
  it('falls back to date for date-only, null when absent', () => {
    expect(formatPricedAsOf('2026-06-02')).toBe('Jun 2, 2026');
    expect(formatPricedAsOf(null)).toBeNull();
  });
});

describe('presentEconomics', () => {
  const credit = {
    max_profit: 35, max_risk: 165, capital_at_risk: 165,
    breakeven_lower: 719.75, breakeven_upper: null,
    net_credit: 35, net_debit: null,
    priced_as_of: '2026-06-02T14:15:00Z', pop: null,
    basis: 'per_contract', legs_complete: true,
  };
  it('formats a put-credit-spread economics object', () => {
    const e = presentEconomics(credit);
    expect(e).not.toBeNull();
    expect(e!.maxProfit).toBe('$35');
    expect(e!.maxRisk).toBe('$165');
    expect(e!.capitalAtRisk).toBe('$165');
    expect(e!.breakeven).toBe('719.75');
    expect(e!.premium).toBe('Credit $35');
    expect(e!.pricedAsOf).toBe('Jun 2, 14:15');
  });
  it('renders a two-sided breakeven for iron condors', () => {
    const e = presentEconomics({ ...credit, breakeven_lower: 747.3, breakeven_upper: 765.7 });
    expect(e!.breakeven).toBe('747.30 – 765.70');
  });
  it('renders debit when net_debit set', () => {
    const e = presentEconomics({ ...credit, net_credit: null, net_debit: 40 });
    expect(e!.premium).toBe('Debit $40');
  });
  it('returns null for null economics', () => {
    expect(presentEconomics(null)).toBeNull();
    expect(presentEconomics(undefined)).toBeNull();
  });
  it('frames risk/reward, 1 on the smaller side', () => {
    const e = presentEconomics(credit)!;             // $35 make / $165 risk
    expect(e.riskRewardLine).toBe('Risk $165 to make $35');
    expect(e.rrRatio).toBe('1 : 4.7');
    const rev = presentEconomics({ ...credit, max_profit: 165, max_risk: 35 })!;
    expect(rev.rrRatio).toBe('4.7 : 1');
  });
  it('hides risk/reward when profit or risk not positive', () => {
    const e = presentEconomics({ ...credit, max_profit: 0 })!;
    expect(e.riskRewardLine).toBeNull();
    expect(e.rrRatio).toBeNull();
  });
});

describe('actionDirective', () => {
  it('qualified → Open regardless of band', () => {
    expect(actionDirective(true, 81)).toEqual({ label: 'Open', tone: 'open' });
  });
  it('not qualified → Consider/Watch/Skip by confidence', () => {
    expect(actionDirective(false, 70)).toEqual({ label: 'Consider', tone: 'consider' });
    expect(actionDirective(false, 55)).toEqual({ label: 'Watch', tone: 'watch' });
    expect(actionDirective(false, 40)).toEqual({ label: 'Skip', tone: 'skip' });
  });
});

describe('presentLegs', () => {
  it('projects persisted legs with human labels; null delta preserved', () => {
    const legs = presentLegs([
      { role: 'short_put', side: 'SELL', option_type: 'PUT', strike: 720,
        expiry: '2026-06-18', entry_mid: 6.815, delta: -0.28, priced_as_of: '2026-06-02T14:15:00Z' },
      { role: 'long_put', side: 'BUY', option_type: 'PUT', strike: 719,
        expiry: '2026-06-18', entry_mid: 6.565, delta: null, priced_as_of: '2026-06-02T14:15:00Z' },
    ]);
    expect(legs[0]).toEqual({
      role: 'Short put', side: 'Sell', optionType: 'Put', strike: '720.00',
      expiry: 'Jun 18, 2026', entryMid: '$6.82', delta: '-0.28', pricedAsOf: 'Jun 2, 14:15',
    });
    expect(legs[1].delta).toBeNull();          // missing delta hidden, not faked
  });
  it('empty for null/undefined', () => {
    expect(presentLegs(null)).toEqual([]);
    expect(presentLegs(undefined)).toEqual([]);
  });
});
