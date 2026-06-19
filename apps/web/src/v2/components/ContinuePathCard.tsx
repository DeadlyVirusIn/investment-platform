// ContinuePathCard — persistent "what next?" on Discover (P1 activation).
// While Day 1 is incomplete it resumes the current step (with a progress bar);
// once complete it shows the next recommended action by practice-position count.

import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { useOnboardingPath } from '../lib/onboardingPath';

export function ContinuePathCard({ paperCount }: { paperCount: number }) {
  const path = useOnboardingPath(paperCount);
  const resuming = path.progress != null;

  return (
    <SurfaceCard variant="highlight" className="p-5 mb-8">
      <p className="font-semibold uppercase" style={{
        fontSize: 10.5, letterSpacing: '0.12em', color: 'var(--muted-foreground)',
      }}>{resuming ? 'Your path' : 'Next step'}</p>
      <p className="font-display ink-primary mt-1" style={{
        fontSize: 18, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
      }}>{path.title}</p>
      <p className="ink-muted leading-relaxed mt-1" style={{ fontSize: 13 }}>{path.blurb}</p>

      {path.progress && (
        <div className="mt-3 max-w-narrative">
          <div className="flex justify-between mb-1.5">
            <span className="ink-fainter" style={{ fontSize: 11 }}>Day 1</span>
            <span className="ink-fainter tabular-nums" style={{ fontSize: 11 }}>
              {path.progress.done} of {path.progress.total}
            </span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden"
            style={{ backgroundColor: 'color-mix(in oklch, var(--brand) 14%, transparent)' }}>
            <div className="h-full" style={{
              width: `${(path.progress.done / path.progress.total) * 100}%`,
              backgroundColor: 'var(--brand)',
            }} />
          </div>
        </div>
      )}

      <Link to={path.to}
        className="inline-flex items-center gap-1.5 mt-4 px-4 h-9 rounded-full"
        style={{ fontSize: 12.5, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}>
        {resuming ? 'Resume' : 'Continue'} <ArrowRight className="size-3.5" aria-hidden />
      </Link>
    </SurfaceCard>
  );
}
