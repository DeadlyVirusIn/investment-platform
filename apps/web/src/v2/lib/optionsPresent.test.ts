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
