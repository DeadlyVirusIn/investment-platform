// V2 App — providers + routes for the /v2/* surface.
//
// Mounts under /v2/* in the existing App.tsx. Wraps every rendered
// page in a <div class="v2-root"> with the data-theme attribute so
// the warm token palette only resolves inside this subtree.

import { Routes, Route, Navigate } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import './styles/v2-tokens.css';

import { ThemeProvider, useTheme } from './chrome/ThemeContext';
import { UserPrefsProvider } from './state/UserPrefsContext';
import { PaperBookProvider } from './state/PaperBook';
import { CommandPaletteProvider } from './chrome/CommandPalette';
import { Onboarding } from './chrome/Onboarding';

import { LearnHome } from './pages/LearnHome';
import { Briefing } from './pages/Briefing';
import { PickPage } from './pages/PickPage';
import { PaperBook } from './pages/PaperBook';
import { TrackRecord } from './pages/TrackRecord';
import { LessonPage } from './pages/LessonPage';

// Screenshot helper — when URL includes ?skipMotion=1, framer-motion
// jumps every component to its final animated state. Headless Chrome
// captures everything below the first FadeIn delay otherwise.
function shouldSkipMotion(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return (
      new URLSearchParams(window.location.search).get('skipMotion') === '1'
    );
  } catch {
    return false;
  }
}

function V2Surface() {
  const { theme } = useTheme();
  return (
    <div className="v2-root" data-theme={theme}>
      <Onboarding />
      <Routes>
        <Route index element={<Navigate to="learn" replace />} />
        <Route path="learn" element={<LearnHome />} />
        <Route path="learn/lesson/:slug" element={<LessonPage />} />
        <Route path="today" element={<Briefing />} />
        <Route path="today/pick/:symbol" element={<PickPage />} />
        <Route path="portfolio" element={<PaperBook />} />
        <Route path="track-record" element={<TrackRecord />} />
        <Route path="*" element={<Navigate to="learn" replace />} />
      </Routes>
    </div>
  );
}

export default function V2App() {
  const skipMotion = shouldSkipMotion();
  return (
    <MotionConfig reducedMotion={skipMotion ? 'always' : 'never'}>
      <ThemeProvider>
        <UserPrefsProvider>
          <PaperBookProvider>
            <CommandPaletteProvider>
              <V2Surface />
            </CommandPaletteProvider>
          </PaperBookProvider>
        </UserPrefsProvider>
      </ThemeProvider>
    </MotionConfig>
  );
}
