// Options availability — single source of truth for whether/how options
// surfaces render across Workspace pages. Derives a coarse state from
// GET /api/options/pipeline-status (via useOptionsVisibility). Read-only.
//
// States drive honest UI: never show a "setup" when stale/disabled or
// when zero engine-compatible candidates exist.

import {
  useOptionsVisibility,
  type OptionsPipelineStatus,
} from './optionsVisibility';

export type OptionsAvailabilityState =
  | 'loading'
  | 'error'
  | 'disabled'      // OPTIONS_ENABLED off
  | 'stale'         // chain old / sandbox — not validated
  | 'no_setups'     // fresh chain but 0 engine-compatible AND 0 research
  | 'research_only' // 0 engine-compatible, but research ideas exist (hybrid)
  | 'ready';        // fresh + engine-compatible > 0

export type AvailTone = 'good' | 'warn' | 'muted' | 'bad';

export interface OptionsAvailability {
  state: OptionsAvailabilityState;
  label: string;          // short badge text
  tone: AvailTone;
  sentence: string;       // one honest line
  chainStale: boolean;
  isSandbox: boolean;
  universe: number;
  compatible: number;
  incompatible: number;
  research: number;   // hybrid: research-family count (== incompatible)
  providerVersion: string | null;
  latestSnapshotAt: string | null;
  data: OptionsPipelineStatus | undefined;
}

function chainAgeHours(iso: string | null): number | null {
  if (!iso) return null;
  const h = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  return Number.isNaN(h) ? null : h;
}

export function useOptionsAvailability(): OptionsAvailability {
  const { data, isLoading, isError } = useOptionsVisibility();

  const cu = data?.candidate_universe;
  const universe = cu?.total ?? 0;
  const compatible = cu?.engine_compatible ?? 0;
  const incompatible = cu?.engine_incompatible ?? 0;
  const pv = data?.chain_provider_version ?? null;
  const latest = data?.options_chain_snapshot_max_ts ?? null;
  const isSandbox = !!pv && pv.toLowerCase().includes('sandbox');
  const ageH = chainAgeHours(latest);
  const chainStale = isSandbox || ageH == null || ageH > 24;

  const research = incompatible;   // research family == engine-incompatible
  const common = {
    chainStale, isSandbox, universe, compatible, incompatible, research,
    providerVersion: pv, latestSnapshotAt: latest, data,
  };

  if (isLoading) {
    return { state: 'loading', label: 'Loading…', tone: 'muted',
      sentence: 'Checking the options engine…', ...common };
  }
  if (isError || !data) {
    return { state: 'error', label: 'Unavailable', tone: 'muted',
      sentence: 'Could not reach the options engine.', ...common };
  }
  if (!data.options_enabled) {
    return { state: 'disabled', label: 'Engine off', tone: 'muted',
      sentence: 'Options engine is disabled (OPTIONS_ENABLED is off).', ...common };
  }
  if (chainStale) {
    return { state: 'stale', label: 'Data stale', tone: 'warn',
      sentence: `Options chain is stale${isSandbox ? ' (sandbox feed)' : ''} — setups not validated against fresh quotes.`,
      ...common };
  }
  if (compatible <= 0) {
    // Hybrid: engine lane empty. If research ideas exist, surface them
    // honestly rather than implying the whole board is empty.
    if (research > 0) {
      return { state: 'research_only', label: 'Research only', tone: 'muted',
        sentence: `No engine-executable setups today — ${research} research idea${research === 1 ? '' : 's'} to explore (structures the engine does not trade).`,
        ...common };
    }
    return { state: 'no_setups', label: 'No setups', tone: 'muted',
      sentence: 'No options setups today.',
      ...common };
  }
  const researchTail = research > 0
    ? ` · ${research} research idea${research === 1 ? '' : 's'}`
    : '';
  return { state: 'ready', label: 'Ready', tone: 'good',
    sentence: `${compatible} engine-executable setup${compatible === 1 ? '' : 's'}${researchTail}.`,
    ...common };
}
