// Journal — the Remember chapter's conversation log.
// Chronologically merges: Arth's memory notes + your reflections +
// your decisions. One stream. Latest first.

import { ArthosPage } from '../chrome/ArthosChrome';
import { MeTabs } from './components/MeTabs';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice, ArthGlyph } from '../chrome/ArthVoice';
import { useMemoryNotes } from '../lib/arth/memory';
import { useDecisions } from '../lib/arth/decisions';
import { useReflections } from '../lib/reflections';
import type { MemoryNote } from '../lib/arth/memory';
import type { Decision } from '../lib/arth/decisions';
import type { Reflection } from '../lib/reflections';

type LogEntry =
  | { kind: 'memory'; ts: string; note: MemoryNote }
  | { kind: 'decision'; ts: string; decision: Decision }
  | { kind: 'reflection'; ts: string; reflection: Reflection };

export function JournalPage() {
  const memory = useMemoryNotes();
  const decisions = useDecisions();
  const reflections = useReflections();

  const stream: LogEntry[] = [
    ...memory.map<LogEntry>((n) => ({ kind: 'memory', ts: n.ts, note: n })),
    ...decisions.map<LogEntry>((d) => ({ kind: 'decision', ts: d.ts, decision: d })),
    ...reflections.map<LogEntry>((r) => ({ kind: 'reflection', ts: r.createdAt, reflection: r })),
  ].sort((a, b) => b.ts.localeCompare(a.ts));

  return (
    <ArthosPage topBarEyebrow="Journal">
      <PageHeader
        eyebrow="Journal"
        title={<>The running conversation<br />between you and Arth.</>}
        description="Every memory Arth keeps about you, every decision you make on his calls, every reflection you write. Newest first. Nothing leaves your device."
      />

      <MeTabs />

      {stream.length === 0 ? (
        <SurfaceCard variant="muted" className="p-8">
          <ArthVoice mode="opening">
            We're at the beginning. Once you read a briefing, follow a call, or
            tell me something, this is where the conversation lives.
          </ArthVoice>
        </SurfaceCard>
      ) : (
        <div className="space-y-3">
          {stream.map((entry, i) => (
            <Entry key={`${entry.kind}-${i}`} entry={entry} />
          ))}
        </div>
      )}
    </ArthosPage>
  );
}

function Entry({ entry }: { entry: LogEntry }) {
  const when = formatWhen(entry.ts);

  if (entry.kind === 'memory') {
    const cat =
      entry.note.category === 'told_me' ? 'You told me' :
      entry.note.category === 'seen'     ? 'I noticed' :
      'Pattern';
    return (
      <SurfaceCard variant="default" className="p-5">
        <Meta tone="arth" when={when} kind={cat} />
        <p className="ink-primary mt-2" style={{ fontSize: 14, lineHeight: 1.5 }}>
          {entry.note.text}
        </p>
      </SurfaceCard>
    );
  }

  if (entry.kind === 'decision') {
    const d = entry.decision;
    const label =
      d.action === 'paper_traded' ? `You opened a paper trade on ${d.symbol}` :
      d.action === 'saved'        ? `You saved ${d.symbol} for later` :
      d.action === 'skipped'      ? `You skipped ${d.symbol}` :
      `You followed ${d.symbol}`;
    return (
      <SurfaceCard variant="default" className="p-5">
        <Meta tone="you" when={when} kind="Decision" />
        <p className="ink-primary mt-2" style={{ fontSize: 14, lineHeight: 1.5 }}>
          {label}
          {d.skip_reason ? ` — ${d.skip_reason}` : ''}
        </p>
        <p
          className="ink-muted mt-2 max-w-narrative"
          style={{ fontSize: 12.5, fontStyle: 'italic' }}
        >
          Thesis at the time: {d.thesis_snapshot.slice(0, 180)}
          {d.thesis_snapshot.length > 180 ? '…' : ''}
        </p>
      </SurfaceCard>
    );
  }

  // reflection
  const r = entry.reflection;
  return (
    <SurfaceCard variant="muted" className="p-5">
      <Meta tone="you" when={when} kind="Reflection" />
      {r.prompt && (
        <p
          className="ink-muted mt-2 italic"
          style={{ fontSize: 12.5 }}
        >
          {r.prompt}
        </p>
      )}
      <p
        className="ink-primary mt-1.5"
        style={{ fontSize: 14, lineHeight: 1.5 }}
      >
        “{r.body}”
      </p>
    </SurfaceCard>
  );
}

function Meta({ tone, when, kind }: {
  tone: 'arth' | 'you'; when: string; kind: string;
}) {
  return (
    <div className="flex items-center gap-2">
      {tone === 'arth' && <ArthGlyph size={20} />}
      <span
        className="font-semibold uppercase"
        style={{
          fontSize: 10,
          letterSpacing: '0.16em',
          color: tone === 'arth' ? 'var(--brand)' : 'var(--muted-foreground)',
        }}
      >
        {kind}
      </span>
      <span
        className="ml-auto font-mono"
        style={{
          fontSize: 11,
          color: 'var(--muted-foreground)',
        }}
      >
        {when}
      </span>
    </div>
  );
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const same =
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate();
  if (same) {
    return `Today · ${d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`;
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
