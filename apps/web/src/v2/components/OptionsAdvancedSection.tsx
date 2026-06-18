// OptionsAdvancedSection — beginner-safe options lane (Sprint M).
//
// Options never vanish, but they are NOT mixed into stock ideas and are
// hidden behind an "Advanced practice" disclosure (collapsed by default).
// Every card uses beginner language only (Time left / Risk level / Why this
// option setup exists / Maximum loss / What would make it fail) — no DTE, IV,
// delta, spread width, or suitability. Read-only: there is no add-to-paper
// options mutation in the engine yet, so the action is "View" only.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ArrowRight } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { useOptionsLanes } from '../lib/optionsLanes';
import { rankSetups } from '../lib/optionsPresent';
import { beginnerOption } from '../lib/optionPlain';
import { optionDetailHref } from './OptionsSetupCard';
import type { PresentedOption } from '../lib/optionsPresent';

const AMBER = 'oklch(0.70 0.14 75)';

function Row({ label, value }: { label: string; value: string }) {
  return (
    <li className="grid grid-cols-[112px_1fr] gap-3 items-baseline py-2"
      style={{ borderTop: '1px solid var(--border)' }}>
      <span className="font-semibold uppercase"
        style={{ fontSize: 10.5, letterSpacing: '0.08em', color: 'var(--muted-foreground)' }}>
        {label}
      </span>
      <span className="ink-primary" style={{ fontSize: 13, lineHeight: 1.5 }}>{value}</span>
    </li>
  );
}

function BeginnerOptionCard({ opt }: { opt: PresentedOption }) {
  const b = beginnerOption(opt);
  return (
    <SurfaceCard variant="default" className="p-5">
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 16 }}>{opt.underlying}</span>
        <span className="ink-muted" style={{ fontSize: 13 }}>{opt.strategyName}</span>
      </div>
      <ul className="mt-2">
        <Row label="Time left" value={b.timeLeft} />
        <Row label="Risk level" value={b.riskLevel} />
        <Row label="Why this exists" value={b.why} />
        <Row label="Maximum loss" value={b.maxLoss} />
        <Row label="What fails it" value={b.whatFails} />
      </ul>
      <div className="mt-4">
        <Link to={optionDetailHref(opt.observationId)}
          className="inline-flex items-center gap-1.5"
          style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}>
          View option idea <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </div>
    </SurfaceCard>
  );
}

export function OptionsAdvancedSection({ alwaysOpen = false }: { alwaysOpen?: boolean }) {
  const [open, setOpen] = useState(false);
  const lanes = useOptionsLanes();

  // Only surface engine setups; if there are none, keep the disclosure but
  // show an honest empty line. Never fabricate options ideas.
  const setups = lanes.state === 'ready_engine' || lanes.state === 'engine_candidates_only'
    ? rankSetups(lanes.engine).slice(0, 4)
    : [];

  const body = (
    <div className={alwaysOpen ? 'space-y-4' : 'mt-4 space-y-4'}>
      <div className="rounded-xl px-4 py-3" style={{
        backgroundColor: `color-mix(in oklch, ${AMBER} 10%, transparent)`,
        border: `1px solid color-mix(in oklch, ${AMBER} 28%, transparent)`,
      }}>
        <p style={{ fontSize: 12.5, fontWeight: 600, color: AMBER }}>
          ⚠ Options are advanced. Practice only. Not recommended for beginners.
        </p>
      </div>

      {setups.length === 0 ? (
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13 }}>
            No options practice setups right now. Check back later.
          </p>
        </SurfaceCard>
      ) : (
        <div className="space-y-3">
          {setups.map((opt) => (
            <BeginnerOptionCard key={`${opt.observationId}-${opt.ruleId}`} opt={opt} />
          ))}
        </div>
      )}
    </div>
  );

  // Tab context (Discover) renders the warning + cards directly — the tab IS
  // the disclosure. Inline context (/v2/today) keeps the collapsible button.
  if (alwaysOpen) return <section className="mb-10">{body}</section>;

  return (
    <section className="mb-10">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 text-left rounded-2xl px-5 py-4"
        style={{ border: '1px solid var(--border)', backgroundColor: 'var(--card)' }}
        aria-expanded={open}
      >
        <span>
          <span className="font-display ink-primary block" style={{
            fontSize: 18, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
          }}>Options Ideas — Advanced Practice</span>
          <span className="ink-muted block mt-0.5" style={{ fontSize: 12.5 }}>
            Separate from stock ideas. Tap to {open ? 'hide' : 'explore'}.
          </span>
        </span>
        <ChevronDown
          className="size-5 shrink-0 transition-transform"
          style={{ transform: open ? 'rotate(180deg)' : 'none', color: 'var(--muted-foreground)' }}
          aria-hidden
        />
      </button>

      {open && body}
    </section>
  );
}
