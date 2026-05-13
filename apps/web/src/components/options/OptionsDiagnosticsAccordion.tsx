// Phase Opt-C1 Step 14 — Diagnostics accordion.
//
// Wraps the existing Opt-A OptionsDiagnosticsCard. Collapsed by
// default. Click to expand. `?view=ops` query param expands by
// default (operator on-call mode).
//
// One-line summary line shows top-level state when collapsed:
// engine state · ThetaData health · scheduler wiring · flag truths.

import { useEffect, useState } from "react";

import OptionsDiagnosticsCard from "./OptionsDiagnosticsCard";
import { useOptionsPipelineStatus } from "@/lib/options/hooks";


function _readOpsViewFromUrl(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.get("view") === "ops";
}


export default function OptionsDiagnosticsAccordion() {
  // ?view=ops expands by default; otherwise collapsed.
  const [open, setOpen] = useState<boolean>(_readOpsViewFromUrl());
  // React to URL changes (back/forward navigation within /options)
  useEffect(() => {
    const onPop = () => setOpen(_readOpsViewFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const { data } = useOptionsPipelineStatus();

  // Build a one-line summary for the collapsed header
  const summary = (() => {
    if (!data) return "loading…";
    const parts: string[] = [];
    parts.push(`engine ${data.engine_state}`);
    if (data.thetadata_health?.state) {
      parts.push(`ThetaData ${data.thetadata_health.state}`);
    }
    parts.push(`${data.scheduler_jobs_count} scheduler row${
      data.scheduler_jobs_count === 1 ? "" : "s"
    }`);
    return parts.join(" · ");
  })();

  return (
    <section
      className="u-card opt-card opt-diag-accordion"
      data-test="options-diagnostics-accordion"
      data-open={open ? "true" : "false"}
    >
      <button
        type="button"
        className="opt-diag-accordion-head"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        <span className="opt-diag-accordion-toggle">{open ? "▾" : "▸"}</span>
        <span className="opt-card-eyebrow">Diagnostics</span>
        <span className="opt-diag-accordion-summary">· {summary}</span>
      </button>
      {open && (
        <div className="opt-diag-accordion-body">
          <OptionsDiagnosticsCard />
        </div>
      )}
    </section>
  );
}
