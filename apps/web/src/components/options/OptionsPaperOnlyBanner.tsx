// Options lifecycle-dormant banner.
//
// HONEST-BANNER directive: the options paper-execution lifecycle is
// intentionally not yet active. The DB schema, worker stubs, research
// surfaces, and observation logs all exist — but the Phase 1A/1B
// bodies that would actually open, fill, and close simulated trades
// have NOT been shipped.
//
// Until they ship, the options pages reflect research, candidates,
// and design surfaces. They do NOT reflect a running simulation.
// This banner discloses that distinction in plain language without
// shame or apology. It frames dormancy as intentional transparency,
// not as broken software.
//
// MUST appear at the top of every page under /options. Static
// frontend tests assert presence in every options page TSX file.

export default function OptionsPaperOnlyBanner() {
  return (
    <div
      role="status"
      data-test="options-lifecycle-dormant-banner"
      className="mb-3 flex flex-col gap-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100"
    >
      <div className="flex items-center gap-2">
        <span aria-hidden="true">⚠</span>
        <span className="font-semibold">
          Options lifecycle is currently dormant
        </span>
      </div>
      <span className="text-amber-200/80 text-xs leading-snug">
        These pages show research, candidates, and observation surfaces.
        No simulated options trades are running — no fills, no closes,
        no P&amp;L. The execution path is intentionally unshipped pending
        Phase 1A / 1B activation.
      </span>
    </div>
  );
}
