// DensityToggle — controlled component. Parent owns state + applies
// data-density to the root. localStorage persistence handled here.

import { useEffect } from "react";


export type Density = "compact" | "cozy" | "spacious";


const KEY = "pi-density";


export function readInitialDensity(): Density {
  if (typeof window === "undefined") return "cozy";
  try {
    const v = window.localStorage.getItem(KEY);
    if (v === "compact" || v === "cozy" || v === "spacious") return v;
  } catch { /* ignore */ }
  return "cozy";
}


export interface DensityToggleProps {
  value: Density;
  onChange: (next: Density) => void;
}


export default function DensityToggle({ value, onChange }: DensityToggleProps) {
  // Persist whenever value changes
  useEffect(() => {
    try { window.localStorage.setItem(KEY, value); } catch { /* ignore */ }
  }, [value]);

  return (
    <div className="density-toggle" role="group" aria-label="Density">
      {(["compact", "cozy", "spacious"] as Density[]).map(d => (
        <button
          key={d}
          type="button"
          className="density-toggle-btn"
          data-active={value === d ? "true" : "false"}
          onClick={() => onChange(d)}
          aria-pressed={value === d}
        >
          {d}
        </button>
      ))}
    </div>
  );
}
