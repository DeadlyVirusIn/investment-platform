// Phase UI-TERMINAL-LAYERS — Layer 2: "Since yesterday" compact diff.
// Derives deltas from equity series + trades + anomalies.

import { useMemo } from "react";
import {
  usePaperEquity, usePaperTrades, useAnomalies, useCurrentState,
} from "@/lib/operator/hooks";
import { Label, fmtPct } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

type ChangeKind = "up" | "down" | "same" | "warn";

interface Change {
  label: string;
  value: string;
  kind: ChangeKind;
}

export default function WhatChanged() {
  const { data: equity } = usePaperEquity();
  const { data: trades } = usePaperTrades();
  const { data: anomalies } = useAnomalies("open");
  const { data: state } = useCurrentState();

  const changes = useMemo<Change[]>(() => {
    const out: Change[] = [];

    // NAV delta — last session daily_pnl from equity series
    if (equity && equity.length >= 2) {
      const last = equity[equity.length - 1];
      const prev = equity[equity.length - 2];
      const pct = ((last.equity - prev.equity) / prev.equity) * 100;
      out.push({
        label: "NAV",
        value: fmtPct(pct, 2),
        kind: pct > 0.05 ? "up" : pct < -0.05 ? "down" : "same",
      });
    }

    // Regime status
    const regime = state?.stress_regime ? "Stress"
      : state?.directional_regime ? "Directional" : "Neutral";
    out.push({
      label: "Regime",
      value: regime,
      kind: state?.stress_regime ? "warn"
        : state?.directional_regime ? "up" : "same",
    });

    // Engine armed/disarmed
    out.push({
      label: "Engine",
      value: state?.fire
        ? `${state.engine} firing`
        : state?.engine && state.engine !== "none"
          ? `${state.engine} idle` : "None",
      kind: state?.fire ? "up" : "same",
    });

    // Phase 11K.1 — recorded state transitions (paper-only).
    if (trades && trades.length > 0) {
      const lastEntry = trades[0]?.entry_date;
      const todayCount = trades.filter(t => t.entry_date === lastEntry).length;
      const openCount = trades.filter(t => t.status === "open").length;
      out.push({
        label: "Recorded state transitions",
        value: todayCount > 0
          ? `+${todayCount} state transition · ${openCount} open`
          : `${openCount} open · no new state transitions`,
        kind: todayCount > 0 ? "up" : "same",
      });
    }

    // Anomalies
    const anomCount = anomalies?.length ?? 0;
    out.push({
      label: "Anomalies",
      value: anomCount === 0 ? "none open" : `${anomCount} open`,
      kind: anomCount === 0 ? "same" : "warn",
    });

    return out;
  }, [equity, trades, anomalies, state]);

  const allStable = changes.every(c => c.kind === "same");

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <Label>Since yesterday</Label>
        <span className={cn("u-chip",
          allStable ? "u-chip-neutral" : "u-chip-accent")}>
          {allStable ? "stable" : "moving"}
        </span>
      </div>
      <div className="space-y-1">
        {changes.map(c => <ChangeRow key={c.label} c={c} />)}
      </div>
    </div>
  );
}

function ChangeRow({ c }: { c: Change }) {
  const glyph = c.kind === "up" ? "▲"
    : c.kind === "down" ? "▼"
    : c.kind === "warn" ? "!"
    : "·";
  const glyphCls = `is-${c.kind}`;
  const valueCls = c.kind === "up" ? "text-success"
    : c.kind === "down" ? "text-danger"
    : c.kind === "warn" ? "text-warning"
    : "text-fg";
  return (
    <div className="u-changed-row">
      <span className={cn("u-changed-glyph", glyphCls)}>{glyph}</span>
      <span className="u-caption text-fg-2">{c.label}</span>
      <span className={cn("u-mono-sm font-semibold", valueCls)}>
        {c.value}
      </span>
    </div>
  );
}
