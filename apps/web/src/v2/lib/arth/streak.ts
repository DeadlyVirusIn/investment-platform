// Arth streak — day counter, increments on first visit per local date.

import { KEYS, readVersioned, writeVersioned, todayKey } from './storage';
import { useArthStore } from './useArthStore';

export interface StreakState {
  current_day: number;
  longest_day: number;
  last_active_date: string | null;    // YYYY-MM-DD
  visit_dates: string[];              // last 90
  grace_remaining: number;            // 1/month
}

const DEFAULT: StreakState = {
  current_day: 0,
  longest_day: 0,
  last_active_date: null,
  visit_dates: [],
  grace_remaining: 1,
};

function diffDays(a: string, b: string): number {
  const da = new Date(a + 'T00:00:00');
  const db = new Date(b + 'T00:00:00');
  return Math.round((db.getTime() - da.getTime()) / (1000 * 60 * 60 * 24));
}

export function tickStreak(): StreakState {
  const today = todayKey();
  const state = readVersioned<StreakState>(KEYS.streak, DEFAULT);

  if (state.last_active_date === today) return state;

  let nextDay = 1;
  let grace = state.grace_remaining;
  if (state.last_active_date) {
    const gap = diffDays(state.last_active_date, today);
    if (gap === 1) nextDay = state.current_day + 1;
    else if (gap === 2 && grace > 0) {
      nextDay = state.current_day + 1;
      grace -= 1;
    } else nextDay = 1;
  }

  const visits = Array.from(new Set([...state.visit_dates, today])).slice(-90);
  const next: StreakState = {
    current_day: nextDay,
    longest_day: Math.max(state.longest_day, nextDay),
    last_active_date: today,
    visit_dates: visits,
    grace_remaining: grace,
  };
  writeVersioned(KEYS.streak, next);
  return next;
}

export function useStreak(): StreakState {
  return useArthStore<StreakState>(KEYS.streak, DEFAULT);
}
