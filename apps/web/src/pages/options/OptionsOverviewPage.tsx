// UX-1 Commit F — Options overview landing page.
//
// Replaces the previous index redirect ("/options" → "/options/chain")
// which dropped a beginner directly onto the densest possible view
// (raw chain table + Greeks). The new landing is summary-first:
//   1. Calm summary of what the options layer is and is not.
//   2. The existing OptionsShadowVisibilityCard (moved here from
//      OptionsLayout so it does not appear twice).
//   3. "Where to go next" map describing each advanced tab in plain
//      English so users can self-select where to dive in.
//
// NO new endpoint, NO new data hook. NO removal of any existing
// page or capability — every advanced tab remains reachable via
// the unchanged tab nav above this Outlet.

import { Link } from "react-router-dom";

import OptionsShadowVisibilityCard from "@/components/personal/OptionsShadowVisibilityCard";


// Map of every advanced sub-route to a one-line plain-English
// description. Mirrors the labels in OptionsLayout's `TABS`
// array — keep them in sync if either changes.
const _TAB_GUIDE: Array<{ to: string; label: string; hint: string }> = [
  {
    to: "/options/chain",
    label: "Chain",
    hint:
      "Raw options chain (strikes, expirations, prices). " +
      "Most beginners never need this.",
  },
  {
    to: "/options/features",
    label: "Features",
    hint:
      "Internal engineering features used to score option " +
      "candidates. Safe to ignore.",
  },
  {
    to: "/options/trades",
    label: "Paper Trades",
    hint:
      "Simulated multi-leg trades placed by the options paper " +
      "engine. Read-only.",
  },
  {
    to: "/options/risk",
    label: "Risk Dashboard",
    hint:
      "Greeks-based risk view (delta / gamma / theta / vega). " +
      "Advanced.",
  },
  {
    to: "/options/observatory",
    label: "Strategy Observatory",
    hint:
      "Catalogue of the strategy templates the system can " +
      "evaluate (long calls, verticals, etc.).",
  },
  {
    to: "/options/performance",
    label: "Paper Performance",
    hint:
      "Outcome scoring of past simulated options trades.",
  },
  {
    to: "/options/diagnostics",
    label: "Diagnostics",
    hint:
      "Engineering breakdown of why each candidate scored what " +
      "it did. Safe to ignore.",
  },
  {
    to: "/options/replay",
    label: "Scenario Replay",
    hint:
      "What-if reruns of the options engine over past dates.",
  },
  {
    to: "/options/evaluation",
    label: "Evaluation",
    hint:
      "Strict / exploratory mode evaluation of options " +
      "candidates. Advanced.",
  },
  {
    to: "/options/decision-support",
    label: "Decision Support",
    hint:
      "Per-candidate scoring + filtering detail. Advanced.",
  },
  {
    to: "/options/decision-framing",
    label: "Decision Framing",
    hint:
      "Operator framing context for an options candidate. " +
      "Advanced.",
  },
];


export default function OptionsOverviewPage() {
  return (
    <div className="space-y-4" data-test="options-overview-page">
      {/* Calm-state intro: tells the operator what the options       */}
      {/* layer is and what they can ignore. NO live data here —      */}
      {/* the Shadow Visibility Card below carries the numbers.       */}
      <section
        className="u-card-tight"
        data-test="options-overview-focus"
        style={{ padding: "14px 18px" }}
      >
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Start here
        </div>
        <p className="u-body text-fg max-w-3xl">
          The options layer is <strong>read-only research</strong>.
          The system explores experimental options strategies on
          paper only — no real money is involved, no orders are
          ever placed. Most users do not need to interact with this
          section at all.
        </p>
        <p className="u-caption-2 text-fg-3 mt-2 max-w-3xl">
          Safe to ignore for now: the deeper tabs below
          (<em>Chain · Features · Diagnostics · Evaluation ·
          Decision Support · Decision Framing</em>) are advanced
          views aimed at users who already know options pricing.
          They contain no actions and never trade on your behalf.
        </p>
      </section>

      {/* Shadow visibility — the actual numbers. Sourced from the */}
      {/* existing /api/options/shadow/summary + pipeline-status  */}
      {/* endpoints. Moved here from OptionsLayout so it appears  */}
      {/* once on the landing rather than persistently on every   */}
      {/* sub-page.                                               */}
      <OptionsShadowVisibilityCard />

      {/* Where to go next — plain-English description of each    */}
      {/* advanced tab. The tab nav at the top of OptionsLayout   */}
      {/* is the actual navigation; this section is just guidance */}
      {/* so the operator can pick the right tab without          */}
      {/* clicking blind.                                         */}
      <section
        className="u-card-tight"
        data-test="options-overview-tab-guide"
      >
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-2">
          Where to go next
        </div>
        <ul className="space-y-1.5">
          {_TAB_GUIDE.map((t) => (
            <li
              key={t.to}
              className="flex items-baseline gap-2 u-caption"
            >
              <Link
                to={t.to}
                className="font-semibold text-zinc-200 hover:underline"
              >
                {t.label}
              </Link>
              <span className="text-zinc-500">— {t.hint}</span>
            </li>
          ))}
        </ul>
        <p className="u-caption-2 text-fg-3 mt-3">
          🛡️ Read-only — every tab in this section is paper trading
          only. Nothing here places real orders.
        </p>
      </section>
    </div>
  );
}
