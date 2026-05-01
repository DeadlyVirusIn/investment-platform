// Phase 11W (Phase F) — Research Intelligence tab on the
// Recommendations page. Reads `/api/research/ticker/:symbol/latest`
// (GET-only) and renders provenance + body OR a fail-closed
// safety panel when the body is unsafe. NEVER renders action
// language. NEVER renders a run button.

import { useEffect, useState } from 'react';
import { scanForbiddenTokens } from '../../lib/research/forbiddenTokens';
import ResearchBanner from './ResearchBanner';
import ResearchByline from './ResearchByline';
import ResearchSafetyFailure from './ResearchSafetyFailure';
import FreshnessBadge from './FreshnessBadge';

interface RunRow {
  id: string;
  symbol: string;
  as_of: string | null;
  provider: string;
  model_id: string | null;
  model_version: string | null;
  prompt_hash: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  operator_id: string | null;
}

interface AgentOutput {
  id: string;
  agent_role: string;
  sequence_no: number;
  body: string | null;
  safety_status: string;
}

interface RunDetail {
  run: RunRow;
  outputs: AgentOutput[];
}

export interface ResearchIntelligenceTabProps {
  symbol?: string;
}

export default function ResearchIntelligenceTab(
  props: ResearchIntelligenceTabProps,
) {
  const symbol = (props.symbol || '').trim().toUpperCase();
  const [latestRun, setLatestRun] = useState<RunRow | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!symbol) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    fetch(`/api/research/ticker/${encodeURIComponent(symbol)}/latest`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        const run = j?.run ?? null;
        setLatestRun(run);
        if (run?.id) {
          return fetch(`/api/research/runs/${encodeURIComponent(run.id)}`, {
            method: 'GET',
            headers: { Accept: 'application/json' },
          })
            .then((rr) => rr.json())
            .then((dd) => {
              if (!cancelled) setDetail(dd);
            });
        }
        setDetail(null);
      })
      .catch(() => {
        if (!cancelled) {
          setLatestRun(null);
          setDetail(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  return (
    <div className="research-intelligence-tab">
      <ResearchBanner context="tab" />
      {loading && <EmptyState text="Loading research artifacts…" />}
      {!loading && !latestRun && (
        <EmptyState text={
          symbol
            ? `No research runs yet for ${symbol}.`
            : 'No research runs yet for this asset.'
        } />
      )}
      {!loading && latestRun && (
        <RunSection run={latestRun} detail={detail} />
      )}
    </div>
  );
}


function EmptyState({ text }: { text: string }) {
  return (
    <div
      style={{
        color: '#616161',
        fontSize: 14,
        padding: '32px 16px',
        textAlign: 'center',
      }}
    >
      {text}
      <div style={{ fontSize: 12, marginTop: 8, color: '#9e9e9e' }}>
        Research orchestration is read-only and operator-controlled.
      </div>
    </div>
  );
}


function RunSection({
  run,
  detail,
}: {
  run: RunRow;
  detail: RunDetail | null;
}) {
  return (
    <div style={{ padding: '12px 8px' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
      }}>
        <span style={{ fontSize: 13, color: '#424242' }}>
          Latest research run
        </span>
        <FreshnessBadge isoTimestamp={run.started_at} />
        <span style={{
          fontSize: 11, color: '#616161',
          background: '#f5f5f5', padding: '2px 6px', borderRadius: 3,
        }}>
          {run.status}
        </span>
      </div>
      <ResearchByline
        provider={run.provider}
        modelId={run.model_id}
        modelVersion={run.model_version}
        promptHash={run.prompt_hash}
        asOf={run.as_of}
        startedAt={run.started_at}
        operatorId={run.operator_id}
      />
      {detail?.outputs?.length ? (
        <div style={{ marginTop: 12 }}>
          {detail.outputs.map((o) => (
            <AgentOutputCard key={o.id} output={o} />
          ))}
        </div>
      ) : null}
    </div>
  );
}


function AgentOutputCard({ output }: { output: AgentOutput }) {
  // Defense in depth: even though the server runs the safety
  // filter, we re-scan client-side and fail closed if anything
  // looks off.
  const body = output.body || '';
  const scan = scanForbiddenTokens(body);
  const unsafe = output.safety_status !== 'safe' || !scan.ok;
  return (
    <div
      style={{
        border: '1px solid #eeeeee',
        borderRadius: 4,
        padding: 12,
        marginBottom: 8,
        background: '#fafafa',
      }}
    >
      <div style={{
        fontSize: 12, color: '#616161', marginBottom: 6,
      }}>
        <strong>{output.agent_role}</strong> · seq {output.sequence_no}
      </div>
      {unsafe ? (
        <ResearchSafetyFailure matched={scan.matched} />
      ) : (
        <div
          style={{
            fontSize: 13, color: '#212121',
            whiteSpace: 'pre-wrap', lineHeight: 1.5,
          }}
        >
          {body}
        </div>
      )}
    </div>
  );
}
