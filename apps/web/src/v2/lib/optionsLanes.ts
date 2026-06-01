// Options lanes — hybrid dual-lane data + 4-state machine (Phase 3, UI-only).
//
// Single source: GET /api/options/opportunities (family-tagged, additive
// fields from d708603). Splits the surface into the engine-executable lane
// and the research lane, and derives the availability-card state from the
// engine lane's above-conviction count.
//
// Read-only. No mutation, no trading, no flag flip, no backend change.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import { useOptionsAvailability } from './optionsAvailability';

export type OptionsFamily = 'engine_executable' | 'research';

export interface OptionsOpportunity {
  observation_id: number;
  underlying: string;
  rule_id: string;
  family: OptionsFamily;
  engine_compatible: boolean;
  above_floor: boolean;
  bias: string;
  directional_view: string;
  composite_score: number;
  dte: number;
  expiry: string | null;
  strike: number;
  option_type: string;
}

interface OpportunitiesResponse {
  count: number;
  engine_executable_count: number;
  research_count: number;
  conviction_floor: number;
  items: OptionsOpportunity[];
}

export type OptionsLaneState =
  | 'loading'
  | 'error'
  | 'disabled'               // OPTIONS_ENABLED off
  | 'stale'                  // chain stale / sandbox — not validated
  | 'ready_engine'           // >=1 engine setup above the conviction floor
  | 'engine_candidates_only' // engine candidates exist, none above floor yet
  | 'research_only'          // no engine candidates, research ideas exist
  | 'no_setups';             // nothing in either lane

export interface OptionsLanes {
  state: OptionsLaneState;
  engine: OptionsOpportunity[];
  research: OptionsOpportunity[];
  engineCount: number;
  engineAboveFloor: number;
  researchCount: number;
  convictionFloor: number;
  isLoading: boolean;
  isError: boolean;
}

export function useOptionsLanes(): OptionsLanes {
  const avail = useOptionsAvailability();
  const q = useQuery<OpportunitiesResponse>({
    queryKey: ['options', 'opportunities', 'lanes'],
    queryFn: () =>
      apiGet<OpportunitiesResponse>('/options/opportunities?limit=200'),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const items = q.data?.items ?? [];
  const engine = items.filter((i) => i.family === 'engine_executable');
  const research = items.filter((i) => i.family === 'research');
  const engineAboveFloor = engine.filter((i) => i.above_floor).length;

  const base = {
    engine,
    research,
    engineCount: engine.length,
    engineAboveFloor,
    researchCount: research.length,
    convictionFloor: q.data?.conviction_floor ?? 0.78,
    isLoading: q.isLoading || avail.state === 'loading',
    isError: q.isError || avail.state === 'error',
  };

  // Chain-state precedence — disabled / stale come from the pipeline-status
  // availability hook; they gate the lanes regardless of any list contents.
  let state: OptionsLaneState;
  if (avail.state === 'disabled') state = 'disabled';
  else if (q.isLoading || avail.state === 'loading') state = 'loading';
  else if (q.isError || avail.state === 'error') state = 'error';
  else if (avail.state === 'stale') state = 'stale';
  else if (engineAboveFloor > 0) state = 'ready_engine';
  else if (engine.length > 0) state = 'engine_candidates_only';
  else if (research.length > 0) state = 'research_only';
  else state = 'no_setups';

  return { state, ...base };
}
