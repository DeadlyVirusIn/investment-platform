// Phase 11F — Flag chip + flag-list renderer.
// Surfaces engine flag tokens with operator-friendly labels.

import {
  FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
  FLAG_MISSING_SETTLEMENT,
  FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
} from '@/lib/options/optionsApi';

export const FLAG_LABELS: Record<string, string> = {
  [FLAG_ASSIGNMENT_SIMPLIFIED_EXIT]: 'Assignment — simplified exit model',
  [FLAG_PIN_RISK_UNCERTAIN_OUTCOME]: 'Pin risk — outcome uncertain',
  [FLAG_MISSING_SETTLEMENT]:         'Missing settlement — expiry unresolved',
  // Pass-through chips for chain-row data quality
  MISSING_IV:                        'Missing IV — model limitation',
  MISSING_GREEKS:                    'Missing Greeks — model limitation',
  // Feature-engine flags
  NO_QUOTES:                         'No quotes — insufficient data',
  NO_SPOT:                           'No spot — feature unavailable',
  NO_PRICE_HISTORY:                  'No price history — insufficient data',
  INSUFFICIENT_IV_HISTORY:           'Insufficient IV history',
  INSUFFICIENT_VOLUME_HISTORY:       'Insufficient volume history',
  NO_30D_EXPIRY:                     'No ~30d expiry available',
  NO_60D_EXPIRY:                     'No ~60d expiry available',
  NO_90D_EXPIRY:                     'No ~90d expiry available',
  NO_25D_PUT:                        'No 25Δ put available',
  NO_25D_CALL:                       'No 25Δ call available',
  NO_OPEN_INTEREST:                  'No open interest',
  NO_VOLUME:                         'No volume',
  NO_CALLS:                          'No calls',
  NO_PUTS:                           'No puts',
};

export function flagLabel(token: string): string {
  return FLAG_LABELS[token] ?? token;
}

const SEVERITY: Record<string, 'high' | 'med' | 'low'> = {
  [FLAG_ASSIGNMENT_SIMPLIFIED_EXIT]: 'high',
  [FLAG_PIN_RISK_UNCERTAIN_OUTCOME]: 'high',
  [FLAG_MISSING_SETTLEMENT]:         'high',
  MISSING_IV:                        'med',
  MISSING_GREEKS:                    'med',
  NO_QUOTES:                         'med',
  NO_SPOT:                           'med',
};

function severityClass(token: string): string {
  const sev = SEVERITY[token] ?? 'low';
  if (sev === 'high') {
    return 'border-red-500/50 bg-red-500/10 text-red-200';
  }
  if (sev === 'med') {
    return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  }
  return 'border-zinc-600/40 bg-zinc-500/10 text-zinc-200';
}

export default function OptionsFlagChip({ token }: { token: string }) {
  return (
    <span
      title={token}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${severityClass(
        token,
      )}`}
    >
      <span aria-hidden="true">⚠</span>
      <span>{flagLabel(token)}</span>
    </span>
  );
}

export function OptionsFlagList({ flags }: { flags: string[] }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {flags.map((f) => (
        <OptionsFlagChip key={f} token={f} />
      ))}
    </div>
  );
}
