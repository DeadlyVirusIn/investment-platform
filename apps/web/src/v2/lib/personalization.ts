// M4 — Honest personalization lens (EXPLANATION ONLY).
//
// Pure, deterministic. NO LLM, NO model, NO network. Given a user's profile and
// metadata ALREADY present on a recommendation, it explains where the idea may
// or may not fit the user. It NEVER changes, scores, ranks, or reorders the
// recommendation — `limitations` says so explicitly.

export interface ProfileLensInput {
  investing_experience: string | null;
  investing_goal: string | null;
  risk_comfort: string | null;
  time_horizon: string | null;
  preferred_style: string | null;
  liquidity_need: string | null;
  options_experience: string | null;
}

export interface RecMeta {
  isOption: boolean;
  action: string | null;                 // effective engine action (Buy/Hold/…)
  confidenceLabel: string | null;        // High/Medium/Low
  tags: string[];                        // engine tags (may hint volatility/risk)
  horizon: 'short' | 'medium' | 'long' | null; // the idea's typical hold
}

export type FitLabel = 'Strong fit' | 'Possible fit' | 'Caution' | 'Not enough profile';

export interface LensResult {
  fit_label: FitLabel;
  fit_reasons: string[];
  caution_reasons: string[];
  profile_fields_used: string[];
  limitations: string;
}

const REQUIRED: (keyof ProfileLensInput)[] = [
  'investing_experience', 'investing_goal', 'risk_comfort', 'time_horizon', 'preferred_style',
];

export const LENS_LIMITATIONS =
  'ArthOS has not changed this recommendation based on your profile — this is context only.';

export function profileComplete(p: ProfileLensInput | null | undefined): boolean {
  return !!p && REQUIRED.every((k) => !!p[k]);
}

export function computeLens(profile: ProfileLensInput | null | undefined, meta: RecMeta): LensResult {
  if (!profileComplete(profile)) {
    return {
      fit_label: 'Not enough profile',
      fit_reasons: [],
      caution_reasons: [],
      profile_fields_used: [],
      limitations: LENS_LIMITATIONS,
    };
  }
  const p = profile as ProfileLensInput;
  const fit: string[] = [];
  const caution: string[] = [];
  const used = new Set<string>();

  // Is the idea on the more-aggressive side? Deterministic from existing meta.
  const aggressive =
    meta.isOption ||
    meta.confidenceLabel === 'Low' ||
    meta.tags.some((t) => /volatil|high.?risk|speculat|aggress/i.test(t));

  // Options suitability
  if (meta.isOption) {
    used.add('options_experience');
    if (!p.options_experience || p.options_experience === 'none') {
      caution.push('This is an options strategy and you noted no options experience.');
    } else if (p.options_experience === 'learning') {
      caution.push("This is an options strategy and you're still learning options.");
    } else {
      fit.push('You have options experience, which matches this options idea.');
    }
    if (p.investing_experience === 'none' || p.investing_experience === 'beginner') {
      used.add('investing_experience');
      caution.push('Options are advanced for where you are in your investing journey.');
    }
  }

  // Risk comfort
  used.add('risk_comfort');
  if (p.risk_comfort === 'low' && aggressive) {
    caution.push('You prefer lower risk; this idea carries more than that.');
  } else if (p.risk_comfort === 'high' && !aggressive) {
    fit.push("You're comfortable with higher risk; this is a relatively measured idea.");
  }

  // Time horizon vs idea horizon
  if (meta.horizon && p.time_horizon) {
    used.add('time_horizon');
    if (p.time_horizon === meta.horizon) {
      fit.push("Your time horizon lines up with this idea's typical hold.");
    } else if (p.time_horizon === 'short' && meta.horizon !== 'short') {
      caution.push('Your horizon is shorter than this idea usually needs.');
    } else if (p.time_horizon === 'long' && meta.horizon === 'short') {
      caution.push('This idea is shorter-term than your usual horizon.');
    }
  }

  // Liquidity need
  if (p.liquidity_need === 'high') {
    used.add('liquidity_need');
    if (meta.isOption || meta.horizon === 'long' || aggressive) {
      caution.push('You may need cash soon; this could tie it up or swing in value.');
    }
  }

  // Preferred style (crude, honest proxy — not a model)
  used.add('preferred_style');
  const ideaStyle = aggressive ? 'growth' : 'steady';
  if (p.preferred_style === 'balanced' || p.preferred_style === ideaStyle) {
    fit.push(`This is broadly consistent with your ${p.preferred_style} style.`);
  } else if (p.preferred_style) {
    caution.push(`This leans ${ideaStyle}, which differs from your ${p.preferred_style} preference.`);
  }

  // Label — hard caution if it's an options idea the user isn't ready for.
  const optionsHardCaution =
    meta.isOption && (!p.options_experience || p.options_experience === 'none' || p.options_experience === 'learning');

  let fit_label: FitLabel;
  if (optionsHardCaution) {
    fit_label = 'Caution';
  } else if (caution.length && fit.length) {
    fit_label = 'Possible fit';
  } else if (caution.length) {
    fit_label = 'Caution';
  } else if (fit.length) {
    fit_label = 'Strong fit';
  } else {
    fit_label = 'Possible fit';
  }

  return {
    fit_label,
    fit_reasons: fit,
    caution_reasons: caution,
    profile_fields_used: [...used],
    limitations: LENS_LIMITATIONS,
  };
}
