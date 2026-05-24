// Arth decision capture — Follow / Paper trade / Skip / Save per rec.

import { KEYS, readVersioned, writeVersioned } from './storage';
import { useArthStore } from './useArthStore';

export type DecisionAction = 'followed' | 'paper_traded' | 'skipped' | 'saved';

export interface Decision {
  id: string;
  rec_id: string;                     // symbol or rec key
  symbol: string;
  action: DecisionAction;
  skip_reason?: string;
  thesis_snapshot: string;
  ts: string;
}

function uid() {
  return `d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function recordDecision(d: Omit<Decision, 'id' | 'ts'>): Decision {
  const dec: Decision = {
    id: uid(),
    ts: new Date().toISOString(),
    ...d,
  };
  const all = readVersioned<Decision[]>(KEYS.decisions, []);
  writeVersioned(KEYS.decisions, [...all, dec]);
  return dec;
}

export function listDecisions(): Decision[] {
  return readVersioned<Decision[]>(KEYS.decisions, []);
}

const EMPTY_DEC: Decision[] = [];
export function useDecisions(): Decision[] {
  return useArthStore<Decision[]>(KEYS.decisions, EMPTY_DEC);
}

export function decisionForToday(rec_id: string): Decision | undefined {
  const today = new Date().toISOString().slice(0, 10);
  return listDecisions().find(
    (d) => d.rec_id === rec_id && d.ts.slice(0, 10) === today,
  );
}
