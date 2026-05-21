// OptionsActionPills — affordance row for opportunity / position cards.
//
// Pure UI affordances; NO execution coupling. Every action either:
//   * opens an in-page drawer (Explain, Compare),
//   * navigates to a deeper read-only surface (Open in research),
//   * triggers a paper bookmark (Save — local-only),
//   * surfaces the disabled "Paper trade" affordance with a clear
//     reason ("Canary dormant — promotion path off") when the gate
//     is off. The button never calls an execution endpoint.

import { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface OptionsActionPillsProps {
  onExplain?: () => void;
  onCompare?: () => void;
  onSave?: () => void;
  onOpenResearch?: () => void;
  /** When `canaryEnabled=false` the paper-trade pill is rendered but
   *  disabled, with a tooltip explaining the gate. */
  canaryEnabled?: boolean;
  /** Custom reason shown when paper-trade is disabled. */
  paperDisabledReason?: string;
  /** Inline trailing slot (e.g. timestamp). */
  trailing?: ReactNode;
  className?: string;
}

function Pill({
  onClick, disabled, title, children, dataTest,
}: {
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
  children: ReactNode;
  dataTest?: string;
}) {
  return (
    <button
      type="button"
      className={cn("opt-action-pill", disabled && "opt-action-pill-disabled")}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      title={title}
      data-test={dataTest}
    >
      {children}
    </button>
  );
}

export default function OptionsActionPills({
  onExplain, onCompare, onSave, onOpenResearch,
  canaryEnabled = false, paperDisabledReason,
  trailing, className,
}: OptionsActionPillsProps) {
  const paperReason = paperDisabledReason
    ?? "Canary dormant — paper-trade promotion path is off.";

  return (
    <div className={cn("opt-action-pills", className)}
         data-test="opt-action-pills">
      {onExplain && (
        <Pill onClick={onExplain} dataTest="opt-action-explain"
              title="Why this setup fits — open the rationale drawer.">
          Explain
        </Pill>
      )}
      {onCompare && (
        <Pill onClick={onCompare} dataTest="opt-action-compare"
              title="Compare against other candidates on the same underlying.">
          Compare
        </Pill>
      )}
      {onOpenResearch && (
        <Pill onClick={onOpenResearch} dataTest="opt-action-research"
              title="Open per-underlying research depth.">
          Open in Research
        </Pill>
      )}
      {onSave && (
        <Pill onClick={onSave} dataTest="opt-action-save"
              title="Save this setup to your shortlist (local).">
          Save
        </Pill>
      )}
      <Pill
        disabled={!canaryEnabled}
        title={canaryEnabled
          ? "Submit a paper trade against the canary portfolio."
          : paperReason}
        dataTest="opt-action-paper-trade"
      >
        Paper trade
      </Pill>
      {trailing && <span className="opt-action-trailing">{trailing}</span>}
    </div>
  );
}
