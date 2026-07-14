// Sprint 7 (Elite ArthOS) — dev-only Trust Center v1 prototype.
// Renders ONLY when VITE_DEV_TRUST_CENTER === '1' (absent by default).
// Owner-facing shape per TRUST_CENTER_V1_SPEC.md. Fixture values below are
// REAL study outputs where they exist (calibration_metrics.json,
// 2026-07-09) and honest status labels everywhere else — nothing
// manufactured: sections without data say so.

type Label =
  | 'proven' | 'preliminary' | 'insufficient_data'
  | 'not_yet_evaluated' | 'degraded' | 'unavailable';

type Section = { title: string; label: Label; body: string; asOf?: string };

const SECTIONS: Section[] = [
  { title: 'System status', label: 'preliminary', body: 'API, workers, and scheduler healthy; exactly-once job claims verified 2026-07-09. Beta software.' },
  { title: 'Data freshness', label: 'preliminary', body: 'Nightly price ingest with provider fallback; freshness engine reports per-table age. Staleness budget alerts not yet wired to this page.' },
  { title: 'Model version', label: 'proven', body: 'Every deployed image carries its exact git commit (GIT_SHA); recommendations carry engine-version + snapshot hashes.', asOf: 'build provenance' },
  { title: 'Feature schema version', label: 'not_yet_evaluated', body: 'Feature ordering hash designed (Sprint 2); not yet stamped in production.' },
  { title: 'Recommendation sample size', label: 'preliminary', body: 'Research DB: 2,809 live Buy recommendations with resolved outcomes (dev-data study, 2026-07-09). Production resolved outcomes remain below the 10-outcome publication gate.' },
  { title: 'Resolved vs unresolved outcomes', label: 'preliminary', body: '7,752 resolved vs 66,364 unresolved in the research DB; production publishes at >=10 closed outcomes.' },
  { title: 'Confidence calibration', label: 'preliminary', body: 'First study (2026-07-09, research data): High-confidence Buys hit 54.4% vs the ~64% the label implies — overconfident; Medium outperformed High. Displayed confidence unchanged; wording review scheduled.' },
  { title: 'Paper record', label: 'preliminary', body: 'Every idea tracked to resolution in the paper book; wins and losses both published.' },
  { title: 'Benchmark comparison', label: 'not_yet_evaluated', body: 'Buy-and-hold and momentum benchmarks land with the Experiment Lab.' },
  { title: 'Known limitations', label: 'proven', body: 'Paper-only; no live trading. Confidence granularity under review (AUC 0.52 in first study). No commission/slippage in the nightly paper track yet.' },
  { title: 'Recent incidents', label: 'proven', body: '2026-07-08: engine jobs traded user practice books (all drained to $0). Fixed same day; 52 books restored from ledger reconstruction; guards + tests added. Full writeup in the incident log.' },
  { title: 'Model / research change log', label: 'preliminary', body: 'P0-5B scheduler self-heal (2026-07-09); attribution + calibration studies (2026-07-09). Registry-backed log lands with research_run.' },
  { title: 'Promoted experiment history', label: 'not_yet_evaluated', body: 'No experiment has ever been promoted to production. The promotion gate (research_run registry) is specified, not built.' },
  { title: 'Current feature flags', label: 'preliminary', body: 'Options subsystem OFF; ML cannot affect trades (kill switch ON); dev previews (attribution, thesis card, this page) OFF in production.' },
];

const LABEL_STYLE: Record<Label, { text: string; color: string }> = {
  proven: { text: 'PROVEN', color: 'var(--brand)' },
  preliminary: { text: 'PRELIMINARY', color: 'oklch(0.70 0.14 75)' },
  insufficient_data: { text: 'INSUFFICIENT DATA', color: 'oklch(0.62 0.19 25)' },
  not_yet_evaluated: { text: 'NOT YET EVALUATED', color: 'var(--muted-foreground)' },
  degraded: { text: 'DEGRADED', color: 'oklch(0.62 0.19 25)' },
  unavailable: { text: 'UNAVAILABLE', color: 'var(--muted-foreground)' },
};

export function trustCenterDevEnabled(): boolean {
  return import.meta.env.VITE_DEV_TRUST_CENTER === '1';
}

export function TrustCenterDev() {
  if (!trustCenterDevEnabled()) return null;
  return (
    <div className="max-w-copy mx-auto py-10 px-5">
      <p className="text-meta ink-fainter mb-1">DEV PREVIEW — OWNER-FACING</p>
      <h1 className="font-serif text-headline ink-primary mb-2">Trust Center</h1>
      <p className="ink-muted text-[13.5px] mb-8 max-w-narrative">
        What ArthOS knows about itself, with honest labels. Nothing here is a
        marketing number: sections without evidence say so.
      </p>
      {SECTIONS.map((s) => (
        <section key={s.title} className="mb-5 pb-4"
          style={{ borderBottom: '1px solid color-mix(in oklch, var(--muted-foreground) 18%, transparent)' }}>
          <div className="flex items-center justify-between gap-3 mb-1">
            <h2 className="ink-primary text-[14px] font-semibold">{s.title}</h2>
            <span className="text-[10px] font-semibold tracking-wider shrink-0"
              style={{ color: LABEL_STYLE[s.label].color }}>
              {LABEL_STYLE[s.label].text}
            </span>
          </div>
          <p className="ink-muted text-[12.5px] leading-relaxed">{s.body}</p>
        </section>
      ))}
      <p className="ink-fainter text-[11px] mt-6">
        Not financial advice. Paper practice only. Labels defined in
        TRUST_CENTER_V1_SPEC.md; live data wiring replaces these fixtures.
      </p>
    </div>
  );
}
