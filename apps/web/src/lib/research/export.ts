// Phase 11W (Phase F.1) — safe markdown export.
//
// Frontend-side helper that renders a research run + its safe agent
// outputs as markdown with the mandatory safety banner at the top.
// NEVER exports unsafe bodies. NEVER includes raw provider output.
// Caller is responsible for triggering the download.

import {
  RESEARCH_BANNER_TEXT,
  scanForbiddenTokens,
} from './forbiddenTokens';

interface RunMeta {
  id: string;
  symbol?: string;
  as_of?: string | null;
  provider?: string;
  model_id?: string | null;
  model_version?: string | null;
  prompt_hash?: string | null;
  started_at?: string | null;
  status?: string;
  operator_id?: string | null;
}

interface AgentOutput {
  agent_role: string;
  sequence_no: number;
  body: string | null;
  safety_status: string;
}

export interface ExportableRun {
  run: RunMeta;
  outputs: AgentOutput[];
}

const _BANNER_LINE = `> ⚠ ${RESEARCH_BANNER_TEXT}`;


function _isSafe(o: AgentOutput): boolean {
  if (o.safety_status !== 'safe') return false;
  if (!o.body) return false;
  return scanForbiddenTokens(o.body).ok;
}


/**
 * Build the markdown export string. Always begins with the safety
 * banner. Unsafe outputs are skipped (never exported, even
 * inline-redacted). When ALL outputs are unsafe, the document still
 * contains banner + provenance + "no exportable safe content"
 * notice.
 */
export function buildSafeMarkdownExport(input: ExportableRun): string {
  const r = input.run;
  const outputs = (input.outputs || []).filter(_isSafe);
  const lines: string[] = [];
  lines.push('# Research note');
  lines.push('');
  lines.push(_BANNER_LINE);
  lines.push('');
  lines.push('## Provenance');
  lines.push('');
  lines.push(`- Symbol: ${r.symbol ?? '—'}`);
  lines.push(`- As of: ${r.as_of ?? '—'}`);
  lines.push(`- Generated at: ${r.started_at ?? '—'}`);
  lines.push(`- Provider: ${r.provider ?? '—'}`);
  lines.push(`- Model: ${r.model_id ?? '—'}` +
              (r.model_version ? `@${r.model_version}` : ''));
  lines.push(`- Prompt hash: ${r.prompt_hash ?? '—'}`);
  if (r.operator_id) lines.push(`- Operator: ${r.operator_id}`);
  lines.push(`- Run id: ${r.id}`);
  lines.push('');
  if (outputs.length === 0) {
    lines.push('## No exportable safe content');
    lines.push('');
    lines.push(
      'No agent output for this run passed the safety filter. ' +
      'Bodies that failed safety are intentionally excluded.',
    );
    lines.push('');
    return lines.join('\n');
  }
  for (const o of outputs) {
    lines.push(`## ${o.agent_role}  (sequence ${o.sequence_no})`);
    lines.push('');
    lines.push(o.body ?? '');
    lines.push('');
  }
  lines.push('---');
  lines.push(_BANNER_LINE);
  lines.push('');
  return lines.join('\n');
}


/**
 * Convenience trigger that downloads the export as a file. Pure
 * client-side; no server POST. Caller chooses the filename. Only
 * mounted by the consuming component when the host page knows
 * `window` is available.
 */
export function triggerSafeMarkdownDownload(
  input: ExportableRun,
  filename = 'research-note.md',
): void {
  const md = buildSafeMarkdownExport(input);
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
