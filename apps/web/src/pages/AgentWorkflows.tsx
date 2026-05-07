// Phase F6 — Agent Workflows page.
//
// Lists every registered agent and lets the operator invoke each
// one on demand. Read-only: every panel renders an envelope with
// a banner reading "Agent-generated insights — read-only research,
// not execution logic." NEVER auto-fetches; every run is gated by
// a button click.

import { useEffect, useState } from "react";

import { Label } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api";


const AGENT_BANNER =
  "Agent-generated insights — read-only research, not execution " +
  "logic.";


type AgentMode = "deterministic";


interface AgentMeta {
  name: string;
  description: string;
  mode: AgentMode;
  inputs: Record<string, string>;
}


interface AgentList {
  banner: string;
  agents: AgentMeta[];
}


interface AgentEnvelope {
  agent: string;
  mode: AgentMode;
  generated_at: string;
  inputs_summary: Record<string, unknown>;
  output: Record<string, unknown>;
  warnings: string[];
  banner: string;
  execution_linked: boolean;
}


export default function AgentWorkflows() {
  const [list, setList] = useState<AgentList | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<AgentList>("/agent-workflows/")
      .then((d) => { if (!cancelled) setList(d); })
      .catch((e) => {
        if (!cancelled) setListError(String(e?.message ?? e));
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="max-w-[1480px] mx-auto px-6 py-6 space-y-5">
      <header>
        <Label>Read-only Research</Label>
        <h1 className="u-title-lg mt-1">Agent Workflows</h1>
        <p className="u-body mt-2 max-w-3xl">
          Deterministic agent pipelines over the existing diagnostic
          endpoints. Every agent is read-only; nothing here writes to
          a trading table or affects execution. Click <strong>Run</strong>
          to invoke an agent — output is freshly computed each time
          and never persisted.
        </p>
        <div
          data-test="agent-workflows-banner"
          className="mt-3 rounded border border-amber-700/60 bg-amber-900/20 px-3 py-2 text-[11px] uppercase tracking-wide text-amber-300"
        >
          {AGENT_BANNER}
        </div>
      </header>

      {listError && (
        <div className="u-card-tight">
          <p className="u-caption text-danger">
            Could not list agents: {listError}
          </p>
        </div>
      )}

      {!list && !listError && (
        <div className="u-card-tight">
          <p className="u-caption italic">Loading agents…</p>
        </div>
      )}

      {list && (
        <section
          data-test="agent-workflows-grid"
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          {list.agents.map((a) => (
            <AgentPanel key={a.name} meta={a} />
          ))}
        </section>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------
// AgentPanel — one card per registered agent
// ---------------------------------------------------------------------

function AgentPanel({ meta }: { meta: AgentMeta }) {
  const [data, setData] = useState<AgentEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const env = await apiGet<AgentEnvelope>(
        `/agent-workflows/${meta.name}/run`,
      );
      setData(env);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <article
      data-test={`agent-panel-${meta.name}`}
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">
            {meta.name}
          </h2>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
            mode: {meta.mode}
          </div>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={loading}
          data-test={`agent-run-${meta.name}`}
          className="rounded border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running…" : "Run"}
        </button>
      </header>

      <p className="u-caption mb-2 text-zinc-300">
        {meta.description}
      </p>

      <details className="mb-2">
        <summary className="u-caption-2 text-zinc-500 cursor-pointer">
          Inputs ({Object.keys(meta.inputs).length})
        </summary>
        <ul className="mt-1 space-y-0.5 text-[11px] text-zinc-400">
          {Object.entries(meta.inputs).map(([k, v]) => (
            <li key={k}>
              <code className="text-zinc-300">{k}</code>{" "}
              <span className="text-zinc-500">— {v}</span>
            </li>
          ))}
        </ul>
      </details>

      {error && (
        <p
          className="u-caption text-danger"
          data-test={`agent-error-${meta.name}`}
        >
          {error}
        </p>
      )}

      {data && (
        <div className="mt-2 space-y-2">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500">
            Generated {data.generated_at}
          </div>
          {data.warnings.length > 0 && (
            <ul
              className="rounded border border-amber-700/60 bg-amber-900/20 px-3 py-2 text-[11px] text-amber-200 space-y-0.5"
              data-test={`agent-warnings-${meta.name}`}
            >
              {data.warnings.map((w, i) => (
                <li key={i}>· {w}</li>
              ))}
            </ul>
          )}
          <pre
            data-test={`agent-output-${meta.name}`}
            className="rounded border border-zinc-800 bg-zinc-950/60 p-3 text-[11px] leading-relaxed text-zinc-300 overflow-x-auto whitespace-pre-wrap break-words max-h-72"
          >
            {JSON.stringify(data.output, null, 2)}
          </pre>
        </div>
      )}
    </article>
  );
}
