// ExpertDetails — small collapsible block for technical rows.
// Default: collapsed. Click to expand. Honest empty state when
// children render nothing.

import { useState, type ReactNode } from "react";


export interface ExpertDetailsProps {
  label?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}


export default function ExpertDetails({
  label = "Technical details",
  children,
  defaultOpen = false,
}: ExpertDetailsProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="expert-details" data-open={open ? "true" : "false"}>
      <button
        type="button"
        className="expert-details-toggle"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span>{label}</span>
        <span className="expert-details-arrow">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="expert-details-body">{children}</div>
      )}
    </div>
  );
}
