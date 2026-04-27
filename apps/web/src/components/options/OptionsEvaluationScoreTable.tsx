// Phase 11H — Score table.
// Neutral styling — no "approved" green for high scores. The score is
// just a number; flags + penalties are surfaced inline so PnL-shaped
// outputs never look "clean" without warnings.

import type {
  EvaluationScoreItem,
  ScoreComponent,
} from '@/lib/options/optionsApi';
import { OptionsFlagList, flagLabel } from './OptionsFlagChip';

function _component(comp: ScoreComponent[] | undefined, name: string): ScoreComponent | null {
  if (!comp) return null;
  return comp.find((c) => c.component === name) ?? null;
}

function ScoreCell({
  comp,
}: { comp: ScoreComponent | null }) {
  if (!comp) return <td className="px-2 py-1 text-right text-zinc-500">—</td>;
  return (
    <td className="px-2 py-1 text-right tabular-nums" title={comp.explanation}>
      {comp.score} / {comp.weight_max}
    </td>
  );
}

function _isQualifiedChip(qualified: boolean) {
  return qualified ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-zinc-700/60 bg-zinc-900/40 px-2 py-0.5 text-[11px] text-zinc-200">
      Candidate rule match
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full border border-zinc-700/60 bg-zinc-900/40 px-2 py-0.5 text-[11px] text-zinc-300">
      Rejected by rule
    </span>
  );
}

export default function OptionsEvaluationScoreTable({
  scores, onSelect,
}: {
  scores: EvaluationScoreItem[];
  onSelect?: (id: string) => void;
}) {
  if (scores.length === 0) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        No evaluation scores in window. Scores are computed only when a
        chain snapshot exists for (symbol, day).
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full text-xs text-zinc-200">
        <thead className="bg-zinc-900/60 text-zinc-400">
          <tr>
            <th className="px-2 py-1 text-left font-medium">Date</th>
            <th className="px-2 py-1 text-left font-medium">Underlying</th>
            <th className="px-2 py-1 text-left font-medium">Strategy</th>
            <th className="px-2 py-1 text-left font-medium">Qualified?</th>
            <th className="px-2 py-1 text-right font-medium">Evaluation</th>
            <th className="px-2 py-1 text-right font-medium">Liquidity</th>
            <th className="px-2 py-1 text-right font-medium">Risk/reward</th>
            <th className="px-2 py-1 text-right font-medium">Volatility</th>
            <th className="px-2 py-1 text-right font-medium">Structure</th>
            <th className="px-2 py-1 text-right font-medium">Penalties</th>
            <th className="px-2 py-1 text-left font-medium">Flags</th>
          </tr>
        </thead>
        <tbody>
          {scores.map((s) => {
            const liq = _component(s.components, 'liquidity');
            const rr  = _component(s.components, 'risk_reward');
            const vol = _component(s.components, 'vol_context');
            const str = _component(s.components, 'structure');
            const penaltyTotal = s.penalties.reduce((acc, p) => acc + p.points, 0);
            return (
              <tr
                key={s.id}
                className="border-b border-zinc-800 hover:bg-zinc-900/50 cursor-pointer"
                onClick={() => onSelect?.(s.id)}
              >
                <td className="px-2 py-1">{s.as_of_date}</td>
                <td className="px-2 py-1">{s.underlying}</td>
                <td className="px-2 py-1">{s.rule_id}</td>
                <td className="px-2 py-1">{_isQualifiedChip(s.qualified)}</td>
                <td className="px-2 py-1 text-right tabular-nums font-semibold">
                  {s.total_score} / 100
                </td>
                <ScoreCell comp={liq} />
                <ScoreCell comp={rr} />
                <ScoreCell comp={vol} />
                <ScoreCell comp={str} />
                <td className="px-2 py-1 text-right tabular-nums">
                  {penaltyTotal === 0 ? '0' : (
                    <span className="text-amber-300">{penaltyTotal}</span>
                  )}
                  {s.penalties.length > 0 ? (
                    <div className="text-[10px] text-zinc-500">
                      {s.penalties[0].label}
                      {s.penalties.length > 1 ? ` +${s.penalties.length - 1}` : ''}
                    </div>
                  ) : null}
                </td>
                <td className="px-2 py-1"><OptionsFlagList flags={s.flags} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export { flagLabel };    // re-export for parent use
