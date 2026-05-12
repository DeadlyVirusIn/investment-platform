// Phase 16 Phase 2 — Ops-only badge consuming /api/intraday-shadow/health.
//
// Read-only operational surface. Renders ONLY on the /ops page; not
// imported by any portfolio / trading / recommendation surface.
//
// Tone discipline:
//   - calm institutional, no flashing, no animated alerts
//   - chip turns warning-tone only when the collection is stale OR
//     the feature flag is off OR the tape has a non-null last_error
//   - red panic is reserved for stale + error states
//   - everything else reads as success-tone or neutral

import { useQuery } from "@tanstack/react-query";

import { Label } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api";
import { cn } from "@/lib/cn";


interface SymbolRow {
  symbol: string;
  rows: number;
}


interface IntradayShadowHealth {
  enabled: boolean;
  now_utc: string | null;
  current_slot_utc: string | null;
  today: {
    date: string;
    row_count: number;
    distinct_symbols: number;
    rows_per_symbol_top_5: SymbolRow[];
    rows_per_symbol_bottom_5: SymbolRow[];
  };
  latest_slot: {
    observed_at_15min: string | null;
    row_count: number;
    cap_hit: boolean;
    cap_threshold: number;
  };
  stale: {
    is_stale: boolean;
    minutes_behind_now: number | null;
    threshold_minutes: number;
  };
  tape: {
    stale: boolean;
    fetched_at_utc: string | null;
    source: string | null;
    last_error: string | null;
    consecutive_errors: number;
  };
  phase_3_progress: {
    lifetime_rows: number;
    lifetime_rows_target: number;
    lifetime_distinct_symbols: number;
    lifetime_distinct_symbols_target: number;
    distinct_dates: number;
    distinct_dates_target: number;
  };
}


function useIntradayShadowHealth() {
  return useQuery<IntradayShadowHealth>({
    queryKey: ["intraday-shadow", "health"],
    queryFn: () => apiGet<IntradayShadowHealth>("/intraday-shadow/health"),
    refetchInterval: 60_000,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}


function fmtTs(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}


function fmtMinutes(n: number | null): string {
  if (n == null) return "—";
  if (n < 1) return `${Math.round(n * 60)}s`;
  if (n < 60) return `${Math.round(n)}m`;
  return `${Math.round(n / 60)}h ${Math.round(n % 60)}m`;
}


function pctBar(value: number, target: number): { pct: number; label: string } {
  const raw = target > 0 ? (value / target) * 100 : 0;
  const pct = Math.max(0, Math.min(100, raw));
  return { pct, label: `${value.toLocaleString()} / ${target.toLocaleString()}` };
}


function ProgressRow({
  k, value, target,
}: { k: string; value: number; target: number }) {
  const { pct, label } = pctBar(value, target);
  const isMet = value >= target;
  return (
    <div className="ish-progress-row">
      <div className="ish-progress-row-head">
        <span className="ish-progress-k">{k}</span>
        <span className={cn("ish-progress-val", isMet && "is-met")}>
          {label}
          {isMet && <span className="ish-progress-tick" aria-hidden="true"> ✓</span>}
        </span>
      </div>
      <div className="ish-progress-track" role="progressbar"
           aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
        <div className="ish-progress-fill" data-met={isMet ? "true" : "false"}
             style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}


function KV({ k, v, tone }: { k: string; v: string; tone?: "pos" | "neg" | "warn" | "neutral" }) {
  return (
    <div className="ish-kv">
      <span className="ish-kv-k">{k}</span>
      <span className={cn("ish-kv-v", tone && `is-${tone}`)}>{v}</span>
    </div>
  );
}


export default function IntradayShadowHealthCard() {
  const { data, isLoading, isError } = useIntradayShadowHealth();

  // ---- loading ----
  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>Intraday Shadow Collection</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  // ---- transport error ----
  if (isError) {
    return (
      <div className="u-card">
        <div className="flex items-center justify-between">
          <Label>Intraday Shadow Collection</Label>
          <span className="u-chip u-chip-warning">unreachable</span>
        </div>
        <div className="u-caption-2 mt-2">/api/intraday-shadow/health did not respond</div>
      </div>
    );
  }

  // ---- main render ----
  const flagOff = !data.enabled;
  const stale = data.stale.is_stale;
  const tapeBad = data.tape.last_error != null || data.tape.consecutive_errors > 0;

  // Status chip — single source of truth for the card's tone
  let chipTone = "u-chip-success";
  let chipLabel = "collecting";
  if (flagOff) { chipTone = "u-chip-neutral"; chipLabel = "disabled"; }
  else if (stale || tapeBad) { chipTone = "u-chip-warning"; chipLabel = "stale"; }

  const latestSlot = fmtTs(data.latest_slot.observed_at_15min);
  const slotDateLabel = data.latest_slot.observed_at_15min
    ? new Date(data.latest_slot.observed_at_15min).toLocaleDateString()
    : "";

  return (
    <div className="u-card">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Intraday Shadow Collection</Label>
          <div className="u-caption-2 mt-0.5">
            {data.enabled ? "live" : "feature flag off"}
            {data.tape.source ? ` · ${data.tape.source}` : ""}
          </div>
        </div>
        <span className={cn("u-chip", chipTone)}
              title="Healthy = collection writing within 30 min of now">
          {chipLabel}
        </span>
      </div>

      {/* Latest slot + cap-hit */}
      <div className="ish-grid-2 mb-3">
        <KV k="Latest slot"
            v={data.latest_slot.observed_at_15min ? `${latestSlot} UTC` : "—"}
            tone={stale ? "warn" : "pos"} />
        <KV k="Behind now"
            v={fmtMinutes(data.stale.minutes_behind_now)}
            tone={stale ? "warn" : "neutral"} />
        <KV k="Latest slot rows"
            v={`${data.latest_slot.row_count} / ${data.latest_slot.cap_threshold}`}
            tone={data.latest_slot.cap_hit ? "warn" : "neutral"} />
        <KV k="Cap hit"
            v={data.latest_slot.cap_hit ? "yes" : "no"}
            tone={data.latest_slot.cap_hit ? "warn" : "neutral"} />
      </div>

      {/* Today's totals */}
      <div className="ish-section-divider" />
      <div className="ish-grid-2 mb-3">
        <KV k="Rows today"
            v={data.today.row_count.toLocaleString()} />
        <KV k="Distinct symbols today"
            v={String(data.today.distinct_symbols)} />
      </div>

      {/* Phase 3 progress bars */}
      <div className="ish-section-divider" />
      <div className="ish-progress-block">
        <div className="ish-progress-block-label">
          Phase 3 gate progress
        </div>
        <ProgressRow
          k="Rows"
          value={data.phase_3_progress.lifetime_rows}
          target={data.phase_3_progress.lifetime_rows_target}
        />
        <ProgressRow
          k="Distinct symbols"
          value={data.phase_3_progress.lifetime_distinct_symbols}
          target={data.phase_3_progress.lifetime_distinct_symbols_target}
        />
        <ProgressRow
          k="Trading-day coverage"
          value={data.phase_3_progress.distinct_dates}
          target={data.phase_3_progress.distinct_dates_target}
        />
      </div>

      {/* Sparse-coverage flag — only when there's a meaningful tail */}
      {data.today.rows_per_symbol_bottom_5.length > 0 && (
        <>
          <div className="ish-section-divider" />
          <div className="ish-caption">
            Sparsest today:{" "}
            {data.today.rows_per_symbol_bottom_5
              .map(r => `${r.symbol} ${r.rows}`)
              .join(" · ")}
          </div>
        </>
      )}

      {/* Tape error footer — only if there's an actual error */}
      {(data.tape.last_error || data.tape.consecutive_errors > 0) && (
        <>
          <div className="ish-section-divider" />
          <div className="ish-caption is-warn">
            Tape: {data.tape.consecutive_errors} consecutive errors
            {data.tape.last_error ? ` · ${data.tape.last_error}` : ""}
          </div>
        </>
      )}

      {/* Disabled-flag info — calm, not alarming */}
      {flagOff && (
        <>
          <div className="ish-section-divider" />
          <div className="ish-caption">
            INTRADAY_ML_SHADOW_ENABLED is off — no rows being written.
            Card stays visible so the operator can confirm the dormant
            state.
          </div>
        </>
      )}

      {/* Slot date footer */}
      <div className="ish-foot mt-3">
        latest slot date {slotDateLabel || "—"} · slot date stamp UTC
      </div>
    </div>
  );
}
