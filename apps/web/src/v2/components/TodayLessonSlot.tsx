// Phase 2D — Today's contextual lesson slot.
//
// Picks the highest-priority lesson hit derived from observed user
// patterns (Phase 2A patternEngine) + streak milestones. Renders
// inline below the Arth opening. Honesty mode: nothing surfaces if
// no trigger has fired.

import { useEffect, useMemo } from 'react';
import { useStreak } from '../lib/arth/streak';
import { useVisiblePatterns } from '../lib/arth/patterns';
import {
  lessonForPattern, lessonForStreakMilestone, type LessonHit,
} from '../lib/arth/lessonRecommender';
import { scanPatterns } from '../lib/arth/patternEngine';
import { seed2dPatternDemo } from '../lib/arth/demoSeed2d';
import { InlineLessonCard } from './InlineLessonCard';

export function TodayLessonSlot() {
  const streak = useStreak();
  const patterns = useVisiblePatterns();

  // Demo seed via ?seed2dLesson=1 (Phase 2D capture only).
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('seed2dLesson') === '1') {
        seed2dPatternDemo();
        scanPatterns();
      }
    } catch { /* ignore */ }
  }, []);

  const hit: LessonHit | null = useMemo(() => {
    // Priority 1: streak milestone (only fires on Day 7 / Day 30).
    const streakHit = lessonForStreakMilestone(streak.current_day);
    if (streakHit) return streakHit;
    // Priority 2: pattern-derived lesson — highest-confidence visible.
    const sortedPatterns = [...patterns].sort((a, b) => {
      const order = { high: 3, medium: 2, low: 1 } as const;
      return order[b.confidence] - order[a.confidence];
    });
    for (const p of sortedPatterns) {
      const h = lessonForPattern(p.rule_key);
      if (h) return h;
    }
    return null;
  }, [streak.current_day, patterns]);

  if (!hit) return null;
  return <InlineLessonCard hit={hit} />;
}
