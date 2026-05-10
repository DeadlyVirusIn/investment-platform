// EmptyStateCard — tasteful placeholder when 0 Buy or 0 Sell.
// Color-outlined to match the missing action.

import type { PickAction } from "@/lib/picks/api";


export interface EmptyStateCardProps {
  action: PickAction;
}


function copy(action: PickAction): { title: string; body: string } {
  switch (action) {
    case "buy":
      return {
        title: "No Buy signals today",
        body: "AI is waiting for stronger upside confirmation. No name has cleared the entry threshold.",
      };
    case "sell":
      return {
        title: "No urgent Sell signals today",
        body: "Risk exists, but no full exit signal has crossed the threshold. Trim or Hold may be appropriate instead.",
      };
    case "trim":
      return { title: "No Trim signals", body: "No positions are flagged for reduction." };
    case "hold":
      return { title: "No Hold signals", body: "No positions are in passive watch mode." };
  }
}


export default function EmptyStateCard({ action }: EmptyStateCardProps) {
  const { title, body } = copy(action);
  return (
    <div className="picks-empty-card" data-action={action} data-test="picks-empty-card">
      <span className="picks-empty-action">{action}</span>
      <h4 className="picks-empty-title">{title}</h4>
      <p className="picks-empty-body">{body}</p>
    </div>
  );
}
