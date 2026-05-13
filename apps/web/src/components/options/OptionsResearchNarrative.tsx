// Phase 6b-3-d — Research narrative layer.
//
// Editorial sentences derived deterministically from analytics
// endpoints. NO LLM-generated prose. NO fake AI commentary. Each
// sentence is a labelled, traceable fact about today's data.
//
// Per the queued 6b-3-d direction:
//   "These should emerge from REAL data. No fake AI prose generation.
//    The point is: translate systems into insight."
//
// Provenance for every line is in code comments — operators can
// trace any sentence back to the analytics endpoint that produced it.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface IntegrityShape {
  coherent_batch_present:    boolean;
  freshness_bound_pass:      boolean;
  universe_closure_pass:     boolean;
  active_batch: null | {
    provider: string;
    provider_version: string;
    age_hours: number;
  };
  today_underlying_count:        number;
  today_out_of_universe_count:   number;
  thresholds: {
    run_universe: string[];
    max_run_chain_age_hours: number;
  };
}

interface RejectionShape {
  rejections: Array<{ reason: string; today: number;
                      delta_pct_vs_avg: number | null }>;
}

interface DailyShape {
  series: Array<{ run_date: string; total: number;
                  would_trade: number; underlyings: number }>;
}

interface ProviderMixShape {
  rows: Array<{ d: string; provider: string;
                provider_version: string; rows_used: number }>;
}


interface NarrativeLine {
  label:    string;
  sentence: string;
  // Provenance: which analytics endpoint produced this fact.
  source:   string;
}


function _buildNarrative(
  integ: IntegrityShape | undefined,
  rej:   RejectionShape | undefined,
  daily: DailyShape | undefined,
  mix:   ProviderMixShape | undefined,
): NarrativeLine[] {
  const out: NarrativeLine[] = [];

  // 1. Coherent batch (provenance + freshness)
  if (integ?.coherent_batch_present && integ.active_batch) {
    out.push({
      label:    "Provider",
      sentence: `${integ.today_underlying_count > 0
                  ? daily?.series?.[0]?.total?.toLocaleString() ?? "—"
                  : "0"} contracts evaluated from a single coherent
                  ${integ.active_batch.provider_version} batch,
                  ${integ.active_batch.age_hours.toFixed(1)} h old.`
                  .replace(/\s+/g, " "),
      source:   "/analytics/integrity + /analytics/daily-counts",
    });
  } else if (integ && !integ.coherent_batch_present) {
    out.push({
      label:    "Provider",
      sentence: "No coherent chain batch is currently available; " +
                "evaluation is paused until the next ingest fires.",
      source:   "/analytics/integrity",
    });
  }

  // 2. Universe state
  if (integ?.universe_closure_pass) {
    const u = integ.thresholds.run_universe;
    out.push({
      label:    "Universe",
      sentence: `All ${u.length} configured underlyings ` +
                `(${u.join(", ")}) surviving liquidity filters; ` +
                `no universe drift.`,
      source:   "/analytics/integrity (universe_closure_pass)",
    });
  } else if (integ && !integ.universe_closure_pass) {
    out.push({
      label:    "Universe",
      sentence: `${integ.today_out_of_universe_count.toLocaleString()} ` +
                `historical decisions reference symbols outside the ` +
                `configured universe — a known artifact preserved ` +
                `from the pre-invariant regime.`,
      source:   "/analytics/integrity (today_out_of_universe_count)",
    });
  }

  // 3. Dominant rejection reason
  if (rej?.rejections && rej.rejections.length > 0) {
    const top = rej.rejections[0];
    const cleanReason = top.reason
      .replace(/^blocked:/, "")
      .replace(/_/g, " ");
    let trend = "";
    if (top.delta_pct_vs_avg != null) {
      const sign = top.delta_pct_vs_avg >= 0 ? "+" : "";
      trend = ` (${sign}${top.delta_pct_vs_avg.toFixed(1)}% vs prior days)`;
    }
    out.push({
      label:    "Rejection pressure",
      sentence: `${cleanReason} dominated today's rejections at ` +
                `${top.today.toLocaleString()} blocked${trend}.`,
      source:   "/analytics/by-rejection",
    });
  }

  // 4. Provider stability
  if (mix?.rows && mix.rows.length > 0) {
    const distinctVersions = new Set(mix.rows.map(r => r.provider_version));
    const latestProvider = mix.rows[0];
    if (distinctVersions.size === 1) {
      out.push({
        label:    "Stability",
        sentence: `${latestProvider.provider_version} stable across ` +
                  `${mix.rows.length} day` +
                  `${mix.rows.length === 1 ? "" : "s"} of observation.`,
        source:   "/analytics/provider-mix",
      });
    } else {
      out.push({
        label:    "Stability",
        sentence: `${distinctVersions.size} distinct provider ` +
                  `versions observed in the trailing window — ` +
                  `learning gates require a single version.`,
        source:   "/analytics/provider-mix",
      });
    }
  }

  return out;
}


export default function OptionsResearchNarrative() {
  const { data: integ } = useQuery<IntegrityShape>({
    queryKey: ["options", "analytics", "integrity"],
    queryFn:  () => apiGet("/options/analytics/integrity"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });
  const { data: rej } = useQuery<RejectionShape>({
    queryKey: ["options", "analytics", "by-rejection", 7],
    queryFn:  () => apiGet("/options/analytics/by-rejection?days=7"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });
  const { data: daily } = useQuery<DailyShape>({
    queryKey: ["options", "analytics", "daily-counts", 1],
    queryFn:  () => apiGet("/options/analytics/daily-counts?days=1"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });
  const { data: mix } = useQuery<ProviderMixShape>({
    queryKey: ["options", "analytics", "provider-mix", 14],
    queryFn:  () => apiGet("/options/analytics/provider-mix?days=14"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const lines = _buildNarrative(integ, rej, daily, mix);

  if (lines.length === 0) return null;

  return (
    <section
      className="u-card opt-narrative"
      data-test="options-research-narrative"
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">
          What the data is showing
        </span>
        <span className="opt-card-meta">
          observations derived from today's data
        </span>
      </header>

      <ul className="opt-narrative-list">
        {lines.map((l) => (
          <li key={l.label} className="opt-narrative-item">
            <span className="opt-narrative-label">{l.label}</span>
            <span className="opt-narrative-sentence">{l.sentence}</span>
          </li>
        ))}
      </ul>

      <p className="u-caption-2 opt-narrative-foot">
        Each observation derives deterministically from the
        analytics endpoints — no generated text, no LLM commentary.
      </p>
    </section>
  );
}
