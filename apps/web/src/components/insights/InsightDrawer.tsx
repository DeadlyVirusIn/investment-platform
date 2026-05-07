// Phase F3 — Insight Drawer.
//
// Read-only research drawer. Renders the markdown body returned by
// /api/insights/{kind} as PLAIN TEXT (whitespace-pre-wrap). Never
// uses dangerouslySetInnerHTML, never spawns a script, never offers
// a "trade", "execute", "rebalance", "optimize", or "apply" button.
// The only action is Close.
//
// Banner is shown verbatim ABOVE the body, sourced from the local
// constant — so even a server response that omitted the banner
// still surfaces the disclaimer to the operator.
//
// State machine (see `InsightStatus` in lib/insights/types):
//   idle      → "Click Explain to fetch a research narrative."
//   loading   → spinner copy
//   ready     → markdown body + meta (model, generated_at)
//   disabled  → 503 copy: insights gated off
//   rejected  → 502 copy: safety layer rejected the body
//   error     → fallback copy with the network/HTTP error message

import { useEffect } from "react";

import {
  INSIGHT_BANNER,
  KIND_LABEL,
  type InsightKind,
  type InsightStatus,
  type InsightSuccess,
} from "@/lib/insights/types";


export interface InsightDrawerProps {
  /** When false the drawer is unmounted. */
  open: boolean;
  /** Subject of the insight. Drives the header label. */
  kind: InsightKind;
  /** Human-readable subtitle: which row / view triggered the fetch. */
  subjectLabel?: string;
  /** Drawer state machine. */
  status: InsightStatus;
  /** Successful payload (only set when `status === "ready"`). */
  data: InsightSuccess | null;
  /** Error / safety-rejection reason. */
  error: string | null;
  /** Close button click. Caller is responsible for resetting the
   *  hook + clearing any local payload state. */
  onClose: () => void;
}


export default function InsightDrawer(props: InsightDrawerProps) {
  const { open, kind, subjectLabel, status, data, error, onClose } = props;

  // Keyboard-dismiss: Escape closes the drawer. Effect runs only
  // while the drawer is open so we never attach a stale listener.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${KIND_LABEL[kind]} research insight`}
      data-test="insight-drawer"
      className="fixed inset-0 z-50 flex items-stretch justify-end"
    >
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close insight drawer"
        onClick={onClose}
        data-test="insight-drawer-scrim"
        className="absolute inset-0 bg-black/50"
      />
      {/* Panel */}
      <aside
        className="relative h-full w-full max-w-xl overflow-y-auto border-l border-zinc-700 bg-zinc-950 p-5 shadow-xl"
        data-test="insight-drawer-panel"
      >
        <Header
          kind={kind}
          subjectLabel={subjectLabel}
          onClose={onClose}
        />
        <BannerRow />
        <Meta data={data} status={status} />
        <Body status={status} data={data} error={error} />
        <Footer />
      </aside>
    </div>
  );
}


// ---------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------

function Header({
  kind, subjectLabel, onClose,
}: {
  kind: InsightKind;
  subjectLabel?: string;
  onClose: () => void;
}) {
  return (
    <header className="mb-3 flex items-start justify-between gap-3">
      <div>
        <div className="text-[10px] uppercase tracking-wide text-zinc-500">
          AI research drawer
        </div>
        <h2 className="mt-0.5 text-base font-semibold text-zinc-100">
          {KIND_LABEL[kind]}
        </h2>
        {subjectLabel && (
          <div className="u-caption-2 text-fg-3 mt-0.5">
            {subjectLabel}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        data-test="insight-drawer-close"
        className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
      >
        Close
      </button>
    </header>
  );
}


function BannerRow() {
  // Always-visible disclaimer. Sourced from the local constant so a
  // truncated/missing-banner server response cannot suppress it.
  return (
    <div
      data-test="insight-drawer-banner"
      className="mb-3 rounded border border-amber-700/60 bg-amber-900/20 px-3 py-2 text-[11px] uppercase tracking-wide text-amber-300"
    >
      {INSIGHT_BANNER}
    </div>
  );
}


function Meta({
  data, status,
}: {
  data: InsightSuccess | null;
  status: InsightStatus;
}) {
  if (status !== "ready" || !data) return null;
  return (
    <div className="mb-3 grid grid-cols-1 gap-1 text-[10px] text-zinc-500">
      <div>
        <span className="uppercase tracking-wide">Source: </span>
        <code>{data.source_endpoint}</code>
      </div>
      <div>
        <span className="uppercase tracking-wide">Model: </span>
        <code>{data.model}</code>
        <span className="ml-3 uppercase tracking-wide">Generated: </span>
        <code>{data.generated_at}</code>
      </div>
    </div>
  );
}


function Body({
  status, data, error,
}: {
  status: InsightStatus;
  data: InsightSuccess | null;
  error: string | null;
}) {
  if (status === "idle") {
    return (
      <p className="u-caption italic text-zinc-500" data-test="insight-state-idle">
        Click the button again to fetch a research narrative.
      </p>
    );
  }
  if (status === "loading") {
    return (
      <p
        className="u-caption italic text-zinc-400"
        data-test="insight-state-loading"
      >
        Fetching insight…
      </p>
    );
  }
  if (status === "disabled") {
    return (
      <div
        data-test="insight-state-disabled"
        className="rounded border border-zinc-700 bg-zinc-900/40 px-3 py-3 text-sm text-zinc-300"
      >
        Agent insights are disabled. Enable{" "}
        <code>AGENT_INSIGHTS_ENABLED</code>{" "}
        only when ready — this drawer is read-only research context
        and never affects trading.
      </div>
    );
  }
  if (status === "rejected") {
    return (
      <div
        data-test="insight-state-rejected"
        className="rounded border border-amber-700/60 bg-amber-900/20 px-3 py-3 text-sm text-amber-200"
      >
        <div className="font-semibold mb-1">
          Insight rejected by safety layer.
        </div>
        <div className="u-caption-2 text-amber-300/80 break-words">
          {error ?? "rejected by safety layer"}
        </div>
      </div>
    );
  }
  if (status === "error") {
    return (
      <div
        data-test="insight-state-error"
        className="rounded border border-red-700/60 bg-red-900/20 px-3 py-3 text-sm text-red-200"
      >
        Insight unavailable. {error ?? ""}
      </div>
    );
  }
  // status === "ready"
  if (!data) return null;
  return (
    <article
      data-test="insight-drawer-content"
      className="rounded border border-zinc-800 bg-zinc-900/40 px-4 py-3 text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap"
    >
      {data.content_markdown}
    </article>
  );
}


function Footer() {
  return (
    <p
      className="mt-4 text-[10px] uppercase tracking-wide text-zinc-600"
      data-test="insight-drawer-footer"
    >
      Read-only · No trade controls · Never affects execution
    </p>
  );
}
