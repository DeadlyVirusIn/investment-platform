// M5 — compact, non-disruptive demand-validation widget. Collect-only.
// Works logged-in and anonymous. Every send is fire-and-forget: a failed
// network request never blocks reading the recommendation (optimistic
// thank-you state). No recommendation data is touched.

import { useState } from 'react';
import { MetaLabel } from '../chrome/ArthosChrome';
import { sendSignal, type FeedbackSurface, type SignalType } from '../../lib/feedback';

function Pill({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="rounded-full px-3.5 h-9 font-medium transition-colors active:scale-95 hover:ink-primary"
      style={{ fontSize: 13, border: '1px solid var(--border)', color: 'var(--muted-foreground)' }}
    >
      {children}
    </button>
  );
}

export function FeedbackWidget({ surface }: { surface: FeedbackSurface }) {
  // Store the chosen label (audit P4): the thank-you echoes the answer so
  // the user sees exactly what was recorded, not just that "something" was.
  const [useful, setUseful] = useState<string | null>(null);
  const [again, setAgain] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [textSent, setTextSent] = useState(false);

  // Fire-and-forget; swallow errors so feedback never blocks the page.
  const fire = (signal: SignalType, value?: string) => {
    sendSignal(surface, signal, value).catch(() => {});
  };

  return (
    <section className="mb-12 max-w-narrative">
      <div className="rounded-xl border border-hairline p-5 sm:p-6">
        <MetaLabel>Help us improve</MetaLabel>

        <div className="mt-3">
          <p className="ink-primary text-[14px] mb-2">Was this explanation useful?</p>
          {useful ? (
            <p className="ink-muted text-[13px]" role="status">Thanks — noted "{useful}".</p>
          ) : (
            <div className="flex gap-2">
              <Pill onClick={() => { setUseful('Yes'); fire('trust_useful', 'yes'); }}>Yes</Pill>
              <Pill onClick={() => { setUseful('Not really'); fire('trust_not_useful', 'no'); }}>Not really</Pill>
            </div>
          )}
        </div>

        <div className="mt-4">
          <p className="ink-primary text-[14px] mb-2">Would you use ArthOS to review another idea?</p>
          {again ? (
            <p className="ink-muted text-[13px]" role="status">Thanks — noted "{again}".</p>
          ) : (
            <div className="flex gap-2">
              <Pill onClick={() => { setAgain('Yes'); fire('would_use_again', 'yes'); }}>Yes</Pill>
              <Pill onClick={() => { setAgain('Not yet'); fire('would_not_use_again', 'not_yet'); }}>Not yet</Pill>
            </div>
          )}
        </div>

        <div className="mt-4">
          <p className="ink-fainter text-[12px] mb-1.5">What would make this more trustworthy? (optional)</p>
          {textSent ? (
            <p className="ink-muted text-[13px]">Thanks for the detail.</p>
          ) : (
            <div className="flex gap-2">
              <input
                type="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Optional"
                style={{
                  flex: 1, height: 38, padding: '0 12px', fontSize: 13, borderRadius: 8,
                  border: '1px solid var(--border)', backgroundColor: 'var(--surface)', color: 'var(--foreground)',
                }}
              />
              <button
                onClick={() => { if (text.trim()) { fire('feedback_text', text.trim()); setTextSent(true); } }}
                disabled={!text.trim()}
                className="rounded-lg px-3.5 h-[38px] font-medium"
                style={{
                  fontSize: 13, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
                  opacity: text.trim() ? 1 : 0.5, cursor: text.trim() ? 'pointer' : 'not-allowed',
                }}
              >
                Send
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
