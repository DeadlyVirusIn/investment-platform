// EmptyStateCard — explains what conditions would trigger this action.

import type { PickAction } from "@/lib/picks/api";
import { emptyStateTriggers } from "@/lib/picks/copilot";


export interface EmptyStateCardProps {
  action: PickAction;
}


export default function EmptyStateCard({ action }: EmptyStateCardProps) {
  const { title, question, conditions } = emptyStateTriggers(action);
  return (
    <div className="picks-empty-card" data-action={action} data-test="picks-empty-card">
      <span className="picks-empty-action">{action}</span>
      <h4 className="picks-empty-title">{title}</h4>
      <p className="picks-empty-question">{question}</p>
      <ul className="picks-empty-conditions">
        {conditions.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </div>
  );
}
