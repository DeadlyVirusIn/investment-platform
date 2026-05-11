// Phase 11F — Risk Dashboard page (read-only).
// Net Greeks (entry-time proxy) + max-loss exposure + expiry concentration
// + flag panel.

import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsRiskSummaryCards from '@/components/options/OptionsRiskSummaryCards';
import OptionsRiskFlagsPanel from '@/components/options/OptionsRiskFlagsPanel';
import { useOptionsRiskSummary } from '@/lib/options/hooks';
import { fmtMoney } from '@/components/options/format';

export default function OptionsRiskDashboardPage() {
  const { data, isLoading, error } = useOptionsRiskSummary();
  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />

      {/* UX-1 Commit O — quiet intro. */}
      <header data-test="options-risk-intro" className="mb-1">
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Pro view · Options risk
        </div>
        <h2 className="text-base font-semibold text-zinc-100">
          Greeks-based exposure for paper options trades
        </h2>
        <p className="u-caption-2 text-fg-3 mt-0.5 max-w-3xl">
          Net delta / gamma / theta / vega and max-loss exposure
          across open paper options positions. Advanced —
          assumes familiarity with options pricing.
        </p>
      </header>

      {isLoading ? (
        <p className="text-sm text-zinc-400">Loading risk summary…</p>
      ) : error ? (
        <p className="text-sm text-red-400">Error loading risk summary.</p>
      ) : data ? (
        <>
          <OptionsRiskSummaryCards data={data} />
          <section className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
            <header className="mb-2 text-xs uppercase tracking-wide text-zinc-400">
              Expiry concentration (open trades)
            </header>
            {data.expiry_concentration.length === 0 ? (
              <p className="text-sm text-zinc-400">
                No open paper trades with legs in the engine.
              </p>
            ) : (
              <div className="u-table-wrap"><table className="w-full text-xs">
                <thead className="text-zinc-500">
                  <tr>
                    <th className="px-2 py-1 text-left">Expiry</th>
                    <th className="px-2 py-1 text-right"># trades</th>
                    <th className="px-2 py-1 text-right">Max loss at expiry</th>
                  </tr>
                </thead>
                <tbody>
                  {data.expiry_concentration.map((r) => (
                    <tr key={r.expiry} className="border-b border-zinc-800">
                      <td className="px-2 py-1">{r.expiry}</td>
                      <td className="px-2 py-1 text-right">{r.n_trades}</td>
                      <td className="px-2 py-1 text-right tabular-nums">
                        {fmtMoney(r.max_loss_at_expiry_dollars)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </section>
          <OptionsRiskFlagsPanel data={data} />
        </>
      ) : null}
    </div>
  );
}
