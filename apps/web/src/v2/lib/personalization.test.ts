import { describe, it, expect } from 'vitest';
import { computeLens, type ProfileLensInput, type RecMeta } from './personalization';

const base: ProfileLensInput = {
  investing_experience: 'intermediate',
  investing_goal: 'grow_wealth',
  risk_comfort: 'medium',
  time_horizon: 'medium',
  preferred_style: 'balanced',
  liquidity_need: 'low',
  options_experience: 'experienced',
};

const stockMeta: RecMeta = { isOption: false, action: 'Buy', confidenceLabel: 'High', tags: [], horizon: 'medium' };
const optionMeta: RecMeta = { isOption: true, action: 'Buy', confidenceLabel: 'Medium', tags: [], horizon: 'short' };

describe('computeLens', () => {
  it('incomplete profile → Not enough profile', () => {
    const r = computeLens({ ...base, risk_comfort: null }, stockMeta);
    expect(r.fit_label).toBe('Not enough profile');
    expect(r.fit_reasons).toEqual([]);
    expect(r.caution_reasons).toEqual([]);
    expect(r.profile_fields_used).toEqual([]);
  });

  it('null profile → Not enough profile', () => {
    expect(computeLens(null, stockMeta).fit_label).toBe('Not enough profile');
  });

  it('low risk + risky idea → surfaces a risk caution (not a Strong fit)', () => {
    const r = computeLens({ ...base, risk_comfort: 'low' }, optionMeta);
    expect(r.caution_reasons.some((c) => /lower risk/i.test(c))).toBe(true);
    expect(r.fit_label).not.toBe('Strong fit');
    expect(r.profile_fields_used).toContain('risk_comfort');
  });

  it('no options experience + options idea → Caution', () => {
    const r = computeLens({ ...base, options_experience: 'none' }, optionMeta);
    expect(r.fit_label).toBe('Caution');
    expect(r.caution_reasons.some((c) => /no options experience/i.test(c))).toBe(true);
    expect(r.profile_fields_used).toContain('options_experience');
  });

  it('matched horizon → fit reason', () => {
    const r = computeLens(base, stockMeta); // time_horizon medium == idea medium
    expect(r.fit_reasons.some((f) => /time horizon lines up/i.test(f))).toBe(true);
    expect(r.profile_fields_used).toContain('time_horizon');
  });

  it('mismatched horizon → caution', () => {
    const r = computeLens({ ...base, time_horizon: 'short' }, stockMeta);
    expect(r.caution_reasons.some((c) => /shorter than/i.test(c))).toBe(true);
  });

  it('mismatched style → caution', () => {
    // aggressive (option) idea vs a steady preference → style caution
    const r = computeLens({ ...base, preferred_style: 'steady', options_experience: 'experienced' }, optionMeta);
    expect(r.caution_reasons.some((c) => /differs from your steady/i.test(c))).toBe(true);
  });

  it('matched style → fit reason', () => {
    const r = computeLens(base, stockMeta); // balanced → broadly consistent
    expect(r.fit_reasons.some((f) => /consistent with your balanced/i.test(f))).toBe(true);
  });

  it('is deterministic', () => {
    const a = JSON.stringify(computeLens(base, optionMeta));
    const b = JSON.stringify(computeLens(base, optionMeta));
    expect(a).toBe(b);
  });

  it('does not mutate the recommendation metadata', () => {
    const meta: RecMeta = { isOption: false, action: 'Buy', confidenceLabel: 'High', tags: ['x'], horizon: 'medium' };
    const snapshot = JSON.stringify(meta);
    computeLens(base, meta);
    expect(JSON.stringify(meta)).toBe(snapshot); // no score/rank/field mutation
  });

  it('always states it did not change the recommendation', () => {
    expect(computeLens(base, stockMeta).limitations).toMatch(/has not changed this recommendation/i);
  });

  // M4A — options coverage
  it('options idea always includes limitations (explanation-only)', () => {
    expect(computeLens(base, optionMeta).limitations).toMatch(/has not changed this recommendation/i);
  });

  it('does not mutate OPTION metadata', () => {
    const meta: RecMeta = { isOption: true, action: null, confidenceLabel: 'Medium', tags: [], horizon: 'short' };
    const snap = JSON.stringify(meta);
    computeLens({ ...base, options_experience: 'none' }, meta);
    expect(JSON.stringify(meta)).toBe(snap);
  });

  it('low/no options experience on an option idea → Caution label + options caution reason', () => {
    for (const oe of ['none', 'learning'] as const) {
      const r = computeLens({ ...base, options_experience: oe }, optionMeta);
      expect(r.fit_label).toBe('Caution');
      expect(r.caution_reasons.some((c) => /options/i.test(c))).toBe(true);
    }
  });

  it('stock lens is unaffected by the options rules (regression)', () => {
    const r = computeLens(base, stockMeta);
    expect(r.caution_reasons.some((c) => /options/i.test(c))).toBe(false);
    expect(r.fit_label).toBe('Strong fit');
  });
});
