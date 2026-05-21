// OptionsPlaybookCard — library tile for a single strategy playbook.
//
// Renders calm summary + bias chip + risk profile. Click → deep dive.

import { Link } from "react-router-dom";

import OptionsBiasChip, { OptionsBias } from "./OptionsBiasChip";


export interface PlaybookLibraryRow {
  rule_id: string;
  executive_summary: string;
  bias: string;
  risk_profile: string;
  directional_view: string;
  related_concepts: string[];
  is_stub: boolean;
}


function strategyDisplayName(s: string): string {
  return s.replace(/_/g, " ").toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}


export default function OptionsPlaybookCard({
  row,
}: { row: PlaybookLibraryRow }) {
  return (
    <Link
      to={`/options/learn/${row.rule_id}`}
      className="opt-playbook-card"
      data-test={`opt-playbook-card-${row.rule_id}`}
      data-bias={row.bias}
    >
      <header className="opt-playbook-card-head">
        <span className="opt-playbook-rule">
          {strategyDisplayName(row.rule_id)}
        </span>
        <OptionsBiasChip bias={row.bias as OptionsBias} size="xs" />
      </header>
      <p className="opt-playbook-summary">{row.executive_summary}</p>
      <div className="opt-playbook-meta">
        <span className="opt-caption-muted">
          {row.risk_profile} risk
        </span>
        {row.is_stub && (
          <span className="opt-playbook-stub-tag">stub</span>
        )}
        {row.related_concepts.length > 0 && (
          <span className="opt-caption-muted">
            {row.related_concepts.length} concept
            {row.related_concepts.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </Link>
  );
}
