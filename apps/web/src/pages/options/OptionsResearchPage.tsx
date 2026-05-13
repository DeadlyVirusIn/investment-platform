// Phase 6b-3-d — Research surface (the workstation).
//
// Composition (5 layers, progressively deepening):
//   1. Pulse strip            — single-line orientation
//   2. High-conviction card   — the #1 observation as editorial feature
//   3. Supporting observations — compact list of #2..#10
//   4. Research narrative     — derived editorial sentences (no LLM)
//   5. Filtered out (collapsible) — rejection histogram + group
//   6. Pathways               — four doorways to sister surfaces
//
// Per the queued 6b-3-d direction:
//   "Research must become the emotional and intellectual center."
//   "Conviction over exhaustiveness."
//   "Hierarchy over density."
//   "Intelligence over diagnostics."
//   "Curation over data dumping."
//
// Discipline:
//   * Read-only. No execution UI. No mutation paths.
//   * Reuses the existing OptionsRejectionsSection +
//     OptionsRejectedCandidatesGroup but DEEPER in the page,
//     beneath conviction layers, not competing with them.
//   * Progressive disclosure: rejection group is collapsible by default.

import { useState } from "react";

import OptionsResearchPulseStrip from
  "@/components/options/OptionsResearchPulseStrip";
import OptionsHighConvictionCard from
  "@/components/options/OptionsHighConvictionCard";
import OptionsSupportingObservations from
  "@/components/options/OptionsSupportingObservations";
import OptionsResearchNarrative from
  "@/components/options/OptionsResearchNarrative";
import OptionsRejectionsSection from
  "@/components/options/OptionsRejectionsSection";
import OptionsRejectedCandidatesGroup from
  "@/components/options/OptionsRejectedCandidatesGroup";
import OptionsResearchPathways from
  "@/components/options/OptionsResearchPathways";


export default function OptionsResearchPage() {
  // The "Filtered out" deeper detail is collapsed by default.
  // The narrative layer above already references the dominant
  // rejection reason — operators only expand if they want to see
  // the full histogram + per-rejection workflow group.
  const [filterDeepOpen, setFilterDeepOpen] = useState(false);

  return (
    <div className="opt-research" data-test="options-research-page">
      {/* 1. Pulse strip — orientation */}
      <OptionsResearchPulseStrip />

      {/* 2. High-conviction observation — editorial feature */}
      <OptionsHighConvictionCard />

      {/* 3. Supporting observations — compact list */}
      <OptionsSupportingObservations />

      {/* 4. Research narrative — derived editorial sentences */}
      <OptionsResearchNarrative />

      {/* 5. Filtered-out deeper detail — collapsible */}
      <section
        className="u-card opt-research-filter-deep"
        data-test="options-research-filter-deep"
        data-open={filterDeepOpen ? "true" : "false"}
      >
        <button
          type="button"
          className="opt-research-filter-deep-head"
          aria-expanded={filterDeepOpen}
          onClick={() => setFilterDeepOpen(o => !o)}
        >
          <span className="opt-research-filter-deep-toggle">
            {filterDeepOpen ? "▾" : "▸"}
          </span>
          <span className="opt-card-eyebrow">
            Filtered-out detail
          </span>
          <span className="opt-research-filter-deep-summary">
            · open the per-reason histogram and rejected candidates
          </span>
        </button>
        {filterDeepOpen && (
          <div className="opt-research-filter-deep-body">
            <OptionsRejectionsSection />
            <OptionsRejectedCandidatesGroup />
          </div>
        )}
      </section>

      {/* 6. Pathways — four editorial doorways */}
      <OptionsResearchPathways />

      {/* By design: the page ends after pathways. */}
    </div>
  );
}
