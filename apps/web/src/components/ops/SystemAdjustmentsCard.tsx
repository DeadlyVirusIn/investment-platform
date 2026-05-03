// Phase SYSTEM-ALPHA-6 — compact "System Adjustments" card for Ops.

import {
  useActiveParams, useApplyCalibration, useCalibrationRecs,
  useRevertCalibration,
} from "@/lib/alpha/calibration";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";


export default function SystemAdjustmentsCard() {
  const { data: recs } = useCalibrationRecs();
  const { data: active } = useActiveParams();
  const apply = useApplyCalibration();
  const revert = useRevertCalibration();

  const recList = recs?.recommendations ?? [];
  const activeEntries = Object.entries(active?.parameters ?? {});

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>System Adjustments</Label>
          <div className="u-caption-2 mt-0.5">
            Deterministic calibration · risk-reducing only
          </div>
        </div>
        <span className={cn("u-chip",
          recList.length ? "u-chip-accent" : "u-chip-neutral")}>
          {recList.length} rec
        </span>
      </div>

      {recList.length === 0 ? (
        <div className="u-caption-2 italic mb-3">
          No adjustments pending. Run{" "}
          <code className="u-mono-sm">
            POST /api/alpha/calibration/refresh
          </code>.
        </div>
      ) : (
        <ul className="divide-y divide-b1 mb-3">
          {recList.map(r => (
            <li key={r.parameter_key} className="py-2.5">
              <div className="flex items-center justify-between mb-1">
                <span className="u-mono-sm text-fg font-semibold">
                  {r.parameter_key}
                </span>
                <span className={cn("u-chip",
                  r.auto_applicable ? "u-chip-success" : "u-chip-warning")}>
                  {r.auto_applicable ? "auto-safe" : "review"}
                </span>
              </div>
              <div className="u-caption text-fg-2 mb-1">
                {r.reason}
              </div>
              <div className="u-caption-2 flex items-center gap-3 mb-2">
                <span>
                  <span className="text-danger">{r.old_value}</span>
                  {" → "}
                  <span className="text-success">{r.new_value}</span>
                </span>
                <span>n={r.sample_size}</span>
                <span>conf {(r.confidence * 100).toFixed(0)}%</span>
              </div>
              <button
                className="u-chip u-chip-accent"
                disabled={apply.isPending}
                onClick={() => apply.mutate(r)}>
                apply
              </button>
            </li>
          ))}
        </ul>
      )}

      {activeEntries.length > 0 && (
        <div className="pt-2 border-t border-b1">
          <div className="u-label-sm mb-2">Active overrides</div>
          <ul className="space-y-1">
            {activeEntries.map(([k, v]) => (
              <li key={k}
                  className="flex items-center justify-between u-caption-2">
                <span className="u-mono-sm text-fg-2">{k}</span>
                <span className="flex items-center gap-2">
                  <span className="u-mono-sm text-fg">{v}</span>
                  <button className="u-chip u-chip-neutral"
                          disabled={revert.isPending}
                          onClick={() => revert.mutate(k)}>
                    revert
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
