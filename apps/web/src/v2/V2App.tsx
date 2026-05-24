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
import { Opportunities } from './pages/Opportunities';
import { Catalysts } from './pages/Catalysts';
import { FieldNotes } from './pages/FieldNotes';
import { Watchlist } from './pages/Watchlist';
// Lovable port (Phase 4) — academy + glossary index surfaces.
import { AcademyPage } from './pages/AcademyPage';
import { GlossaryIndex } from './pages/GlossaryIndex';
// UX Phase 2 — guided coach surfaces.
import { StartHere } from './pages/StartHere';
import { MePage } from './pages/MePage';
import { Methodology } from './pages/Methodology';
// UX Phase 3A — close-the-loop surfaces.
import { TryFromLesson } from './pages/TryFromLesson';
import { ReflectionsReview } from './pages/ReflectionsReview';
// Arth MVP — Journal (Remember chapter — conversation log).
import { JournalPage } from './pages/JournalPage';

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
        {/* UX Phase 2 — guided coach surfaces. */}
        <Route path="start" element={<StartHere />} />
        <Route path="me" element={<MePage />} />
        <Route path="methodology" element={<Methodology />} />
        {/* UX Phase 3A — close-the-loop surfaces. */}
        <Route path="try/:lessonSlug" element={<TryFromLesson />} />
        <Route path="reflections" element={<ReflectionsReview />} />
        {/* Arth MVP — Journal route, the Remember chapter surface. */}
        <Route path="journal" element={<JournalPage />} />
        <Route path="learn" element={<LearnHome />} />
        <Route path="learn/lesson/:slug" element={<LessonPage />} />
        {/* Lovable port (Phase 4) — academy + glossary index. */}
        <Route path="learn/stocks" element={<AcademyPage pathSlug="how-markets-actually-work" />} />
        <Route path="learn/risk" element={<AcademyPage pathSlug="risk-literacy" />} />
        <Route path="learn/options" element={<AcademyPage pathSlug="options-literacy" />} />
        <Route path="learn/glossary" element={<GlossaryIndex />} />
        <Route path="today" element={<Briefing />} />
        <Route path="today/pick/:symbol" element={<PickPage />} />
        <Route path="opportunities" element={<Opportunities />} />
        <Route path="catalysts" element={<Catalysts />} />
        <Route path="field-notes" element={<FieldNotes />} />
        <Route path="watchlist" element={<Watchlist />} />
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
