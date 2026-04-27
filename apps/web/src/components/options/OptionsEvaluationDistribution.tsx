// Phase 11H — historical score distribution by strategy + by underlying.

import type { EvaluationDistribution } from '@/lib/options/optionsApi';

function _val(v: string | null, nullText = 'Insufficient data'): string {
  if (v === null || v === undefined) return nullText;
  return v;
}

function BucketRow({
  label, n, mean,
  buckets,
}: {
  label: string;
  n: number;
  mean: string | null;
  buckets: { lo: number; hi: number; count: number }[];
}) {
  return (
    <tr className="border-b border-zinc-800">
      <td className="px-2 py-1">{label}</td>
      <td className="px-2 py-1 text-right tabular-nums">{n}</td>
      <td className="px-2 py-1 text-right tabular-nums">{_val(mean)}</td>
      {buckets.map((b) => (
        <td key={`${b.lo}-${b.hi}`} className="px-2 py-1 text-right tabular-nums">
          {b.count}
        </td>
      ))}
    </tr>
  );
}

export default function OptionsEvaluationDistribution({
  data,
}: { data: EvaluationDistribution }) {
  const bucketHeaders = data.buckets_definition.map((b) => `${b.lo}-${b.hi}`);
  return (
    <div className="space-y-4">
      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">By strategy</h2>
        {data.by_strategy.length === 0 ? (
          <div className="text-sm text-zinc-400">No data in window.</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Strategy</th>
                <th className="px-2 py-1 text-right">N</th>
                <th className="px-2 py-1 text-right">Mean</th>
                {bucketHeaders.map((h) => (
                  <th key={h} className="px-2 py-1 text-right">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.by_strategy.map((r) => (
                <BucketRow
                  key={r.strategy}
                  label={r.strategy}
                  n={r.n}
                  mean={r.mean_score}
                  buckets={r.buckets}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">By underlying</h2>
        {data.by_underlying.length === 0 ? (
          <div className="text-sm text-zinc-400">No data in window.</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Underlying</th>
                <th className="px-2 py-1 text-right">N</th>
                <th className="px-2 py-1 text-right">Mean</th>
                {bucketHeaders.map((h) => (
                  <th key={h} className="px-2 py-1 text-right">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.by_underlying.map((r) => (
                <BucketRow
                  key={r.underlying}
                  label={r.underlying}
                  n={r.n}
                  mean={r.mean_score}
                  buckets={r.buckets}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
