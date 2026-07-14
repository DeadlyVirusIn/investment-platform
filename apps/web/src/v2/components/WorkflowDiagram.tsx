// Workflow Diagram (investor-demo, Task 2).
//
// An investor-facing, screenshot-worthy explanation of how an idea travels
// through ArthOS: Market Data → Analysis → Bull vs Bear → Recommendation →
// Paper Portfolio → Track Record → Reflection. Presentation only — static
// copy describing the real pipeline; no data, no logic.

const STEPS: { n: string; title: string; desc: string }[] = [
  { n: '01', title: 'Market data', desc: 'Live prices and signals across thousands of names, every day.' },
  { n: '02', title: 'Analysis', desc: 'The engine scores each name on trend, momentum, and risk.' },
  { n: '03', title: 'Bull vs bear', desc: 'Both sides of every idea, weighed honestly — not just the pitch.' },
  { n: '04', title: 'Recommendation', desc: 'A clear call — buy, hold, or step back — with the working shown.' },
  { n: '05', title: 'Paper portfolio', desc: 'Follow it with practice money. Nothing real is ever at risk.' },
  { n: '06', title: 'Track record', desc: 'Every call is recorded — an honest, auditable history you own.' },
  { n: '07', title: 'Reflection', desc: 'Closed ideas are graded: what we expected, happened, and learned.' },
];

export function WorkflowDiagram() {
  return (
    <section className="mb-16 sm:mb-20">
      <div className="text-[12px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--brand)' }}>
        How an idea flows
      </div>
      <h2 className="font-serif ink-primary text-[24px] sm:text-[28px] leading-tight mb-7 max-w-[24ch]">
        One pipeline, end to end — from the market to a lesson.
      </h2>

      <ol className="relative">
        {/* vertical rail */}
        <div
          className="absolute left-[15px] top-2 bottom-2 w-px"
          style={{ background: 'var(--hairline,#e5e5e5)' }}
          aria-hidden
        />
        {STEPS.map((s, i) => (
          <li key={s.n} className={`relative flex gap-5 ${i === STEPS.length - 1 ? '' : 'pb-7'}`}>
            <div
              className="relative z-10 shrink-0 flex items-center justify-center rounded-full font-serif tabular-nums"
              style={{
                width: 32, height: 32,
                background: 'var(--surface-base)',
                border: '1px solid var(--brand)',
                color: 'var(--brand)',
                fontSize: 13,
              }}
            >
              {s.n}
            </div>
            <div className="pt-1">
              <div className="ink-primary font-semibold text-[15px] leading-tight">{s.title}</div>
              <p className="ink-muted text-[14px] leading-snug mt-1 max-w-narrative">{s.desc}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
