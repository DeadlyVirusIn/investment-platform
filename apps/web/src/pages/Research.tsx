// Phase UI3 — Research tab. Consolidates recommendations + accepted buys +
// missed opportunities off the main Control Center.

import { useState } from "react";
import Recommendations from "@/pages/Recommendations";

const TABS = [
  { id: "recommendations", label: "Recommendations" },
  { id: "accepted", label: "Accepted" },
  { id: "missed", label: "Missed" },
] as const;

type TabId = typeof TABS[number]["id"];

export default function Research() {
  const [tab, setTab] = useState<TabId>("recommendations");

  return (
    <div className="min-h-screen bg-surface">
      <div className="max-w-[1440px] mx-auto px-6 py-8">
        <header className="mb-6">
          <h1 className="text-[11px] uppercase tracking-[0.3em] text-text-muted
                         font-semibold">
            Research
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Non-production observations: recommendations, accepted ideas,
            missed setups.
          </p>
        </header>

        <nav className="flex gap-1 mb-6 border-b border-surface-border">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`text-xs px-4 py-2 border-b-2 transition-colors
                ${tab === t.id
                  ? "border-accent text-text-primary font-medium"
                  : "border-transparent text-text-muted hover:text-text-primary"}`}>
              {t.label}
            </button>
          ))}
        </nav>

        <div>
          {tab === "recommendations" && <Recommendations />}
          {tab === "accepted" && (
            <div className="text-sm text-text-muted py-12 text-center">
              Accepted ideas view — to be populated.
            </div>
          )}
          {tab === "missed" && (
            <div className="text-sm text-text-muted py-12 text-center">
              Missed opportunities view — to be populated.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
