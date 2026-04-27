// Phase 11F — Paper-only banner.
// MUST appear at the top of every page under /options.
// Static frontend tests assert presence in every options page TSX file.

export default function OptionsPaperOnlyBanner() {
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100"
    >
      <span aria-hidden="true">⚠</span>
      <span className="font-semibold">Options are paper-trading only</span>
      <span className="text-amber-200/80">
        — simulated lifecycle. No live orders. No execution. No ML signals.
      </span>
    </div>
  );
}
