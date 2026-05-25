// Arth opening — the first voice the user hears in the See chapter.
// Composed from streak + yesterday's decision + briefing object.
// Runs streak tick + seeds declared memory from onboarding on mount.

import { useEffect, useMemo, useRef } from 'react';
import { useStreak, tickStreak } from '../lib/arth/streak';
import { listDecisions } from '../lib/arth/decisions';
import { addMemory, listMemory } from '../lib/arth/memory';
import { generateBriefing } from '../lib/arth/briefing';
import { todayKey } from '../lib/arth/storage';
import { logEvent } from '../lib/arth/events';
import { useUserPrefs } from '../state/UserPrefsContext';
import { ArthVoice } from '../chrome/ArthVoice';

export function ArthOpening() {
  const streak = useStreak();
  const { level, topics, dailyReadingTime } = useUserPrefs();
  // Guard one-time per-session side-effects against React StrictMode +
  // useLocalValue subscriber storms. Without this, logEvent would
  // re-fire each render and create an infinite update loop.
  const didInit = useRef(false);

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;

    tickStreak();
    logEvent('see', 'session_open');
    logEvent('see', 'briefing_viewed');

    // Seed declared memory from onboarding once (dedupe in addMemory
    // protects against re-seed across sessions).
    const existing = listMemory();
    const hasOnboardingMemory = existing.some(
      (m) => m.source === 'onboarding' && m.category === 'told_me',
    );
    if (!hasOnboardingMemory && level) {
      addMemory({
        category: 'told_me',
        text: `You told me your level is "${level}".`,
        source: 'onboarding',
        pinned: true,
      });
      if (topics.length > 0) {
        addMemory({
          category: 'told_me',
          text: `You picked these interests: ${topics.join(', ')}.`,
          source: 'onboarding',
          pinned: true,
        });
      }
      if (dailyReadingTime) {
        addMemory({
          category: 'told_me',
          text: `You said you read around ${dailyReadingTime}.`,
          source: 'onboarding',
        });
      }
    }
  // Run once. Reading level/topics through closure is fine — they're
  // localStorage-derived and stable within a session for our purposes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const opening = useMemo(() => {
    // Find yesterday's most recent decision for opening voice.
    const all = listDecisions();
    const today = new Date().toISOString().slice(0, 10);
    const lastBeforeToday = [...all]
      .filter((d) => d.ts.slice(0, 10) !== today)
      .sort((a, b) => b.ts.localeCompare(a.ts))[0];
    const briefing = generateBriefing({
      todayKey: todayKey(),
      streakDay: streak.current_day || 1,
      yesterdayDecision: lastBeforeToday
        ? { action: lastBeforeToday.action, symbol: lastBeforeToday.symbol }
        : undefined,
    });
    return briefing.arth_opening;
  }, [streak.current_day]);

  return (
    <div className="mb-8">
      <ArthVoice mode="opening">{opening}</ArthVoice>
      {streak.current_day > 0 && (
        <p
          className="ink-fainter mt-2 ml-9 font-mono tabular-nums uppercase"
          style={{ fontSize: 10, letterSpacing: '0.16em' }}
        >
          Day {streak.current_day}
          {streak.longest_day > streak.current_day
            ? ` · longest ${streak.longest_day}`
            : ''}
        </p>
      )}
    </div>
  );
}
