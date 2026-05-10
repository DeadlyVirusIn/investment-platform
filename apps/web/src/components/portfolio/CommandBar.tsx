// CommandBar — premium portfolio intelligence strip.
// 9 KPI cards with real data (or "—" when absent).

import { useEffect, useState } from "react";

import { fetchCommandBar, fmtCurrency, fmtPct, fmtSigned, type CommandBarData } from "@/lib/portfolio/api";


interface KpiCardProps {
  label: string;
  value: string;
  tone?: "default" | "good" | "bad" | "warn";
  hint?: string;
}


function KpiCard({ label, value, tone = "default", hint }: KpiCardProps) {
  return (
    <div className="pi-kpi" data-tone={tone}>
      <div className="pi-kpi-label">{label}</div>
      <div className="pi-kpi-value">{value}</div>
      {hint && <div className="pi-kpi-hint">{hint}</div>}
    </div>
  );
}


function toneFor(n: number | null): "default" | "good" | "bad" {
  if (n == null) return "default";
  if (n > 0) return "good";
  if (n < 0) return "bad";
  return "default";
}


export default function CommandBar() {
  const [data, setData] = useState<CommandBarData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchCommandBar()
      .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <section className="pi-cmdbar pi-cmdbar-loading" data-test="pi-cmdbar">
        <div className="pi-cmdbar-skeleton" />
      </section>
    );
  }

  if (!data) return null;

  return (
    <section className="pi-cmdbar" data-test="pi-cmdbar">
      <KpiCard label="Total NAV" value={fmtCurrency(data.totalNav, { compact: true })} />
      <KpiCard label="Open P&L" value={fmtSigned(data.openPnl)} tone={toneFor(data.openPnl)} />
      <KpiCard label="Realized P&L" value={fmtSigned(data.realizedPnl)} tone={toneFor(data.realizedPnl)} />
      <KpiCard label="Total Return" value={fmtPct(data.totalReturnPct)} tone={toneFor(data.totalReturnPct)} />
      <KpiCard label="Monthly Premium" value={fmtCurrency(data.monthlyPremium, { compact: true })} tone={data.monthlyPremium && data.monthlyPremium > 0 ? "good" : "default"} />
      <KpiCard label="Active Strategies" value={data.activeStrategies != null ? String(data.activeStrategies) : "—"} />
      <KpiCard label="Portfolio Risk" value={data.portfolioRiskLabel ?? "—"} tone={data.portfolioRiskLabel === "high" ? "bad" : data.portfolioRiskLabel === "low" ? "good" : "default"} />
      <KpiCard label="Cash Available" value={fmtCurrency(data.cashAvailable, { compact: true })} />
      <KpiCard label="AI Posture" value={data.posture ?? "—"} hint={data.freshAt ?? undefined} />
    </section>
  );
}
