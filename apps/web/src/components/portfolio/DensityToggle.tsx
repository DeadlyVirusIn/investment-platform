// DensityToggle — beginner / cozy / spacious density.
// Sets [data-density] on the .picks-root container. Persisted in
// localStorage["pi-density"]. CSS reads the attribute.

import { useEffect, useState } from "react";


export type Density = "compact" | "cozy" | "spacious";


const KEY = "pi-density";


function readInitial(): Density {
  if (typeof window === "undefined") return "cozy";
  try {
    const v = window.localStorage.getItem(KEY);
    if (v === "compact" || v === "cozy" || v === "spacious") return v;
  } catch { /* ignore */ }
  return "cozy";
}


function applyDensity(d: Density) {
  if (typeof document === "undefined") return;
  const root = document.querySelector(".picks-root");
  if (root) (root as HTMLElement).setAttribute("data-density", d);
}


export default function DensityToggle() {
  const [density, setDensity] = useState<Density>(() => readInitial());

  useEffect(() => {
    applyDensity(density);
    try { window.localStorage.setItem(KEY, density); } catch { /* ignore */ }
  }, [density]);

  // Re-apply when .picks-root mounts (in case toggle renders before page)
  useEffect(() => {
    const id = window.setTimeout(() => applyDensity(density), 0);
    return () => window.clearTimeout(id);
  }, [density]);

  return (
    <div className="density-toggle" role="group" aria-label="Density">
      {(["compact", "cozy", "spacious"] as Density[]).map(d => (
        <button
          key={d}
          type="button"
          className="density-toggle-btn"
          data-active={density === d ? "true" : "false"}
          onClick={() => setDensity(d)}
          aria-pressed={density === d}
        >
          {d}
        </button>
      ))}
    </div>
  );
}
