// Phase 2E — Mentor Profile.
//
// Replaces the metric-dashboard Me page with a relationship document
// keyed to "what Arth has learned about me." Honors all Phase 2A
// pattern guardrails. Honesty mode: missing evidence → "Too early to
// tell." — never speculation.

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { MeTabs } from './components/MeTabs';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice, ArthGlyph } from '../chrome/ArthVoice';
import { useStreak } from '../lib/arth/streak';
import { useMemoryNotes } from '../lib/arth/memory';
import {
  useVisiblePatterns, confirmPattern, disputePattern, confidenceHedge,
  type PatternObservation,
} from '../lib/arth/patterns';
import { useCompetence, type CompetenceEntry } from '../lib/arth/competence';
import { deriveStrengths, deriveBlindSpots, type StrengthBlindEntry } from '../lib/arth/strengths';
import { useEvents } from '../lib/arth/events';
import { useDecisions } from '../lib/arth/decisions';
import { CONTEXTUAL_LESSONS } from '../lib/arth/contextualLessons';
import { seed2eMentorDemo } from '../lib/arth/demoSeed2e';
import { useSession } from '../state/SessionContext';
import { getProfile, type ProfileData } from '../../lib/profile';

const PROFILE_LABELS: Record<keyof Pick<ProfileData, 'investing_experience' | 'investing_goal' | 'risk_comfort' | 'time_horizon' | 'preferred_style'>, Record<string, string>> = {
  investing_experience: { none: 'New to investing', beginner: 'Beginner', intermediate: 'Intermediate', experienced: 'Experienced' },
  investing_goal: { learn: 'Learn the ropes', grow_wealth: 'Grow wealth', income: 'Generate income', preserve: 'Preserve capital', retirement: 'Retirement' },
  risk_comfort: { low: 'Low', medium: 'Medium', high: 'High' },
  time_horizon: { short: 'Short (under 1 yr)', medium: 'Medium (1–5 yrs)', long: 'Long (5+ yrs)' },
  preferred_style: { steady: 'Steady', balanced: 'Balanced', growth: 'Growth' },
};

const PROFILE_ROWS: { key: keyof typeof PROFILE_LABELS; label: string }[] = [
  { key: 'investing_experience', label: 'Experience' },
  { key: 'investing_goal', label: 'Goal' },
  { key: 'risk_comfort', label: 'Risk comfort' },
  { key: 'time_horizon', label: 'Horizon' },
  { key: 'preferred_style', label: 'Style' },
];

function profileAnswerRows(profile: ProfileData | null) {
  if (!profile) return [];
  return PROFILE_ROWS.flatMap(({ key, label }) => {
    const value = profile[key];
    const answer = value ? PROFILE_LABELS[key][value] : undefined;
    return answer ? [{ label, answer }] : [];
  });
}

export function MentorProfile() {
  // Demo seed via ?seedMentor=1 (capture only).
  useEffect(() => {
    try {
      if (new URLSearchParams(window.location.search).get('seedMentor') === '1') {
        seed2eMentorDemo();
      }
    } catch { /* ignore */ }
  }, []);

  const { authenticated, loading: sessionLoading } = useSession();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    if (sessionLoading) return;
    if (!authenticated) {
      setProfile(null);
      setProfileLoading(false);
      return;
    }
    setProfileLoading(true);
    getProfile()
      .then((response) => { if (alive) setProfile(response.profile); })
      .catch(() => { if (alive) setProfile(null); })
      .finally(() => { if (alive) setProfileLoading(false); });
    return () => { alive = false; };
  }, [authenticated, sessionLoading]);

  const streak = useStreak();
  const memory = useMemoryNotes();
  const patterns = useVisiblePatterns();
  const competence = useCompetence();
  const events = useEvents();
  const decisions = useDecisions();

  const profileRows = profileAnswerRows(profile);
  const seen = memory.filter((m) => m.category === 'seen' && !m.retired).slice(0, 5);

  const strengths = useMemo(() => deriveStrengths(), [events, decisions]);
  const blindSpots = useMemo(() => deriveBlindSpots(), [decisions]);

  // Recent lesson events with their trigger context.
  const recentLessons = useMemo(() => {
    return events
      .filter((e) => e.kind === 'lesson_opened' && e.entity)
      .slice(-5)
      .reverse()
      .map((e) => ({
        slug: e.entity as string,
        ts: e.ts,
        lesson: CONTEXTUAL_LESSONS[e.entity as string],
        tier: (e.meta?.tier as string) ?? 'primer',
        trigger: (e.meta?.trigger as string) ?? undefined,
      }))
      .filter((r) => r.lesson);
  }, [events]);

  return (
    <ArthosPage topBarEyebrow="Me">
      <PageHeader
        eyebrow="Mentor profile"
        title={<>What Arth has<br />learned about you.</>}
        description="This page is the running record of our relationship. Every section answers a question I've been asked enough times to bother writing it down: what have you told me, what have I seen you do, what do I think I'm seeing — and where the evidence runs out."
      />

      <MeTabs />

      <StreakHero streak={streak} />

      <Section title="What you've told me">
        {!profileLoading && profileRows.length === 0 && (
          <TooEarly>
            Answer a few profile questions and what you tell me will live here. <Link to="/profile" className="ink-primary underline">Answer questions →</Link>
          </TooEarly>
        )}
        {!profileLoading && profileRows.length > 0 && (
          <div className="space-y-2">
            {profileRows.map((row) => (
              <p key={row.label} className="ink-primary" style={{ fontSize: 14, lineHeight: 1.55 }}>
                <span className="ink-muted">{row.label} — </span>{row.answer}
              </p>
            ))}
            <Link to="/profile" className="inline-block ink-primary underline pt-1" style={{ fontSize: 13 }}>
              Edit →
            </Link>
          </div>
        )}
      </Section>

      <Section title="What I've seen you do">
        {seen.length === 0 ? (
          <TooEarly>I haven't seen you act on enough recommendations yet. This will fill in as you follow, skip, or save calls.</TooEarly>
        ) : (
          <div className="space-y-2">
            {seen.map((m) => (
              <Bullet key={m.id} tone="seen">{m.text}</Bullet>
            ))}
          </div>
        )}
      </Section>

      <Section title="Patterns I'm watching">
        <ArthVoice mode="advisory" className="mb-4">
          Patterns are behavioral, not personality. Each one needs at least five observations before I'll show it. You can confirm or dispute — disputed patterns pause for 30 days before I'll bring them back.
        </ArthVoice>
        {patterns.length === 0 ? (
          <TooEarly>No patterns surfaced yet. I need at least 5 observations of the same kind before showing one.</TooEarly>
        ) : (
          <div className="space-y-3">
            {patterns.map((p) => <PatternCard key={p.id} pattern={p} />)}
          </div>
        )}
      </Section>

      <Section title="Strengths I've noticed">
        {strengths.length === 0 ? (
          <TooEarly>Strengths surface only when I have at least 5 observations supporting them. Keep showing up and these will fill in.</TooEarly>
        ) : (
          <div className="space-y-3">
            {strengths.map((s) => <EvidenceCard key={s.id} entry={s} />)}
          </div>
        )}
      </Section>

      <Section title="Blind spots I've noticed">
        {blindSpots.length === 0 ? (
          <TooEarly>Blind spots surface only when I have at least 5 observations. None to flag yet.</TooEarly>
        ) : (
          <div className="space-y-3">
            {blindSpots.map((b) => <EvidenceCard key={b.id} entry={b} />)}
          </div>
        )}
      </Section>

      <Section title="Competence map">
        <CompetenceMap competence={competence} />
      </Section>

      <Section title="Recent lessons I surfaced for you">
        {recentLessons.length === 0 ? (
          <TooEarly>I'll record lessons here as I surface them — and tell you exactly which trigger fired each time.</TooEarly>
        ) : (
          <div className="space-y-3">
            {recentLessons.map((r, i) => (
              <SurfaceCard key={i} variant="muted" className="p-4">
                <div className="flex items-start gap-2 mb-1">
                  <ArthGlyph size={18} />
                  <span className="font-mono ink-muted" style={{ fontSize: 11.5 }}>
                    {new Date(r.ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </span>
                  <span className="ml-auto font-semibold uppercase" style={{
                    fontSize: 9.5, letterSpacing: '0.14em', color: 'var(--brand)',
                  }}>{r.tier}</span>
                </div>
                <p className="font-display ink-primary" style={{
                  fontSize: 15, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
                }}>{r.lesson?.title ?? r.slug}</p>
                {r.trigger && (
                  <p className="ink-muted italic mt-1" style={{ fontSize: 12 }}>
                    Why I surfaced it: {r.trigger}
                  </p>
                )}
              </SurfaceCard>
            ))}
          </div>
        )}
      </Section>

      <Section title="Where to go next">
        <NextRitual />
      </Section>

      <Section title="Track record (quiet metrics)">
        <QuietMetrics events={events} decisions={decisions} competence={competence} />
      </Section>
    </ArthosPage>
  );
}

// ─── Streak hero ────────────────────────────────────────────────

function StreakHero({ streak }: { streak: ReturnType<typeof useStreak> }) {
  const dots = useMemo(() => {
    const out: ('on' | 'off')[] = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = 16; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const k = d.toISOString().slice(0, 10);
      out.push(streak.visit_dates.includes(k) ? 'on' : 'off');
    }
    return out;
  }, [streak.visit_dates]);

  return (
    <SurfaceCard variant="highlight" className="p-6 lg:p-7 mb-10">
      <div className="flex items-center gap-3 mb-3">
        <ArthGlyph size={28} />
        <p className="font-semibold uppercase" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)',
        }}>Day {streak.current_day || 0} of practice</p>
      </div>
      <p className="font-display ink-primary mb-2" style={{
        fontSize: 28, lineHeight: 1.15,
        fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
      }}>
        {streak.current_day === 0
          ? "We're just starting."
          : streak.current_day === streak.longest_day
            ? "Longest streak — and still going."
            : `Longest streak so far: ${streak.longest_day}.`}
      </p>
      <p className="ink-muted" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
        Showing up is half the work. Days I've seen you below:
      </p>
      <div className="mt-3 flex items-center gap-1 flex-wrap">
        {dots.map((s, i) => (
          <span key={i} aria-hidden style={{
            width: 10, height: 10, borderRadius: 999,
            backgroundColor: s === 'on'
              ? 'var(--brand)'
              : 'color-mix(in oklch, var(--ink-fainter) 30%, transparent)',
          }} />
        ))}
        <span className="ink-fainter ml-2" style={{ fontSize: 11 }}>
          Last 17 days
        </span>
      </div>
    </SurfaceCard>
  );
}

// ─── Pattern card with confirm/dispute ──────────────────────────

function PatternCard({ pattern }: { pattern: PatternObservation }) {
  const hedge = confidenceHedge(pattern.confidence);
  return (
    <SurfaceCard variant="muted" className="p-4">
      <div className="flex items-start gap-2 mb-1">
        <ArthGlyph size={18} />
        <p className="ink-muted italic" style={{ fontSize: 12 }}>
          {hedge} — {pattern.observation_count} observations, confidence {pattern.confidence}
        </p>
      </div>
      <p className="ink-primary mt-1" style={{ fontSize: 14, lineHeight: 1.55 }}>
        {pattern.text}
      </p>
      <div className="mt-3 flex items-center gap-2 flex-wrap">
        {pattern.user_confirmed ? (
          <span className="ink-muted italic" style={{ fontSize: 12 }}>
            You confirmed this. I'll keep weighting it.
          </span>
        ) : (
          <>
            <ChipBtn brand onClick={() => confirmPattern(pattern.id)}>
              Yes, that's me
            </ChipBtn>
            <ChipBtn onClick={() => disputePattern(pattern.id)}>
              No, I had reasons
            </ChipBtn>
          </>
        )}
      </div>
    </SurfaceCard>
  );
}

// ─── Evidence-backed strength / blind-spot ──────────────────────

function EvidenceCard({ entry }: { entry: StrengthBlindEntry }) {
  const accent = entry.category === 'strength' ? 'var(--brand)' : 'var(--destructive)';
  return (
    <SurfaceCard variant="default" className="p-4">
      <div className="flex items-start gap-2 mb-1">
        <ArthGlyph size={18} />
        <span className="font-semibold uppercase" style={{
          fontSize: 10, letterSpacing: '0.14em', color: accent,
        }}>
          {entry.category === 'strength' ? 'Strength' : 'Blind spot'} · {entry.confidence} confidence
        </span>
      </div>
      <p className="ink-primary mt-1" style={{ fontSize: 14, lineHeight: 1.55 }}>
        {entry.text}
      </p>
      <p className="ink-muted italic mt-2" style={{ fontSize: 12.5 }}>
        Evidence: {entry.evidence_summary}
      </p>
    </SurfaceCard>
  );
}

// ─── Competence map ─────────────────────────────────────────────

function CompetenceMap({ competence }: { competence: CompetenceEntry[] }) {
  const knownLessonSlugs = Object.keys(CONTEXTUAL_LESSONS);
  // Group by status.
  const byStatus = {
    recalled:    competence.filter((c) => c.status === 'recalled'),
    learned:     competence.filter((c) => c.status === 'learned'),
    read:        competence.filter((c) => c.status === 'read'),
    encountered: competence.filter((c) => c.status === 'encountered'),
  };
  const seenSlugs = new Set(competence.map((c) => c.lesson_slug));
  const untaughtCount = knownLessonSlugs.filter((s) => !seenSlugs.has(s)).length;
  const totalKnown = knownLessonSlugs.length;

  // Suggest next concept: pick the first untaught lesson from catalogue.
  const nextSlug = knownLessonSlugs.find((s) => !seenSlugs.has(s));
  const nextLesson = nextSlug ? CONTEXTUAL_LESSONS[nextSlug] : null;

  if (competence.length === 0) {
    return (
      <TooEarly>
        Your competence map starts populating as I surface lessons during your decisions. After your first skip-with-reason or trade outcome, this section will show what you've encountered, read, and learned.
      </TooEarly>
    );
  }

  return (
    <>
      <p className="ink-muted mb-4" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
        {byStatus.learned.length + byStatus.recalled.length} of {totalKnown} concepts learned ·{' '}
        {byStatus.read.length} read but unchecked ·{' '}
        {byStatus.encountered.length} encountered ·{' '}
        {untaughtCount} not yet shown.
      </p>
      <div className="space-y-3">
        <CompetenceRow label="Recalled" tone="brand" rows={byStatus.recalled} />
        <CompetenceRow label="Learned (passed the check)" tone="brand" rows={byStatus.learned} />
        <CompetenceRow label="Read (not yet checked)" tone="muted" rows={byStatus.read} />
        <CompetenceRow label="Encountered" tone="muted" rows={byStatus.encountered} />
      </div>
      {nextLesson && (
        <SurfaceCard variant="muted" className="p-4 mt-5">
          <p className="font-semibold uppercase mb-1" style={{
            fontSize: 10, letterSpacing: '0.14em', color: 'var(--brand)',
          }}>Next concept I'd suggest</p>
          <p className="ink-primary" style={{ fontSize: 14 }}>
            <strong className="font-display"
              style={{ fontFamily: "'Instrument Serif', ui-serif, Georgia, serif" }}>
              {nextLesson.title}
            </strong> · {nextLesson.reads_in.primer_seconds}s primer
          </p>
          <p className="ink-muted mt-1" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
            I'll surface this naturally when a relevant trigger fires — but you can also start it whenever.
          </p>
        </SurfaceCard>
      )}
    </>
  );
}

function CompetenceRow({ label, tone, rows }: {
  label: string; tone: 'brand' | 'muted'; rows: CompetenceEntry[];
}) {
  if (rows.length === 0) return null;
  const accent = tone === 'brand' ? 'var(--brand)' : 'var(--muted-foreground)';
  return (
    <div className="grid grid-cols-[180px_1fr] gap-3 items-baseline py-2"
         style={{ borderTop: '1px solid var(--border)' }}>
      <span className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.14em', color: accent,
      }}>{label}</span>
      <ul className="flex flex-wrap gap-1.5">
        {rows.map((c) => {
          const lesson = CONTEXTUAL_LESSONS[c.lesson_slug];
          return (
            <li key={c.lesson_slug} className="px-2 py-0.5 rounded-full" style={{
              fontSize: 11.5,
              backgroundColor: tone === 'brand'
                ? 'color-mix(in oklch, var(--brand) 12%, transparent)'
                : 'var(--card)',
              border: '1px solid var(--border)',
              color: 'var(--foreground)',
            }}>{lesson?.title ?? c.lesson_slug}</li>
          );
        })}
      </ul>
    </div>
  );
}

// ─── Next ritual ────────────────────────────────────────────────

function NextRitual() {
  // Pure copy for now — Phase 2F will compute from session state.
  return (
    <SurfaceCard variant="default" className="p-5">
      <ArthVoice mode="advisory">
        Tomorrow: come back for the next briefing. If you skipped today's call,
        I'll show you a different one. If you followed it, I'll check in when
        it resolves.
      </ArthVoice>
      <div className="mt-4 flex items-center gap-2 flex-wrap">
        <Link to="/today" className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
          fontSize: 12.5, fontWeight: 600,
          backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
        }}>Go to today's briefing →</Link>
        <Link to="/journal" className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
          fontSize: 12.5, fontWeight: 500,
          border: '1px solid var(--border)',
          backgroundColor: 'transparent', color: 'var(--foreground)',
        }}>Open your journal</Link>
        <Link to="/arth" className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
          fontSize: 12.5, fontWeight: 500,
          border: '1px solid var(--border)',
          backgroundColor: 'transparent', color: 'var(--foreground)',
        }}>See my track record</Link>
      </div>
    </SurfaceCard>
  );
}

// ─── Quiet metrics (demoted from old dashboard) ─────────────────

function QuietMetrics({
  events, decisions, competence,
}: {
  events: ReturnType<typeof useEvents>;
  decisions: ReturnType<typeof useDecisions>;
  competence: CompetenceEntry[];
}) {
  const reflections = events.filter((e) => e.kind === 'reflection_written').length;
  const followsCount = decisions.filter(
    (d) => d.action === 'paper_traded' || d.action === 'followed',
  ).length;
  const closed = decisions.filter((d) => d.outcome).length;
  const learned = competence.filter(
    (c) => c.status === 'learned' || c.status === 'recalled',
  ).length;
  return (
    <SurfaceCard variant="muted" className="p-5">
      <p className="ink-muted mb-3" style={{ fontSize: 12.5, fontStyle: 'italic' }}>
        Numbers without narrative. The honest part of the dashboard, demoted to a footer.
      </p>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Reflections" value={String(reflections)} />
        <Stat label="Calls followed" value={String(followsCount)} />
        <Stat label="Closed positions" value={String(closed)} />
        <Stat label="Concepts learned" value={String(learned)} />
      </div>
    </SurfaceCard>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>{label}</p>
      <p className="font-mono ink-primary tabular-nums" style={{
        fontSize: 22, marginTop: 2,
      }}>{value}</p>
    </div>
  );
}

// ─── Shared bits ────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2 className="font-display ink-primary mb-4" style={{
        fontSize: 22, lineHeight: 1.2,
        fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
      }}>{title}</h2>
      {children}
    </section>
  );
}

function Bullet({ tone, children }: { tone: 'declared' | 'seen'; children: React.ReactNode }) {
  const accent = tone === 'declared' ? 'var(--brand)' : 'var(--accent)';
  return (
    <div className="flex items-start gap-2.5">
      <span aria-hidden style={{
        width: 6, height: 6, borderRadius: 999, backgroundColor: accent,
        marginTop: 8, flexShrink: 0,
      }} />
      <p className="ink-primary" style={{ fontSize: 14, lineHeight: 1.55 }}>
        {children}
      </p>
    </div>
  );
}

function TooEarly({ children }: { children: React.ReactNode }) {
  return (
    <SurfaceCard variant="muted" className="p-4">
      <div className="flex items-start gap-2">
        <ArthGlyph size={18} />
        <div>
          <p className="font-semibold uppercase mb-1" style={{
            fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Too early to tell</p>
          <p className="ink-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
            {children}
          </p>
        </div>
      </div>
    </SurfaceCard>
  );
}

function ChipBtn({ brand, onClick, children }: {
  brand?: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button onClick={onClick} className="px-3 py-1 rounded-full" style={{
      fontSize: 12, fontWeight: 600,
      backgroundColor: brand ? 'var(--brand)' : 'var(--card)',
      color: brand ? 'var(--brand-foreground)' : 'var(--foreground)',
      border: '1px solid var(--border)',
    }}>{children}</button>
  );
}
