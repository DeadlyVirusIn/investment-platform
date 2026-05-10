// CommandBar — smart KPIs that hide-or-explain when data missing.
// Never shows a giant dash. Each metric either has a real value or
// is collapsed into a small "connection state" card.

import { useEffect, useState } from "react";

import { fetchCommandBar, fmtCurrency, fmtPct, fmtSigned, type CommandBarData } from "@/lib/portfolio/api";


type Tone = "default" | "good" | "bad" | "warn";


interface Metric {
  key: string;
  label: string;
  value: string;
  tone: Tone;
  hint?: string;
}


function toneFor(n: number | null): Tone {
  if (n == null) return "default";
  if (n > 0) return "good";
  if (n < 0) return "bad";
  return "default";
}


function buildMetrics(d: CommandBarData): { available: Metric[]; missing: string[] } {
  const available: Metric[] = [];
  const missing: string[] = [];

  if (d.totalNav != null) {
    available.push({ key: "nav", label: "Total NAV", value: fmtCurrency(d.totalNav, { compact: true }), tone: "default" });
  } else missing.push("Portfolio NAV");

  if (d.openPnl != null) {
    available.push({ key: "open", label: "Open P&L", value: fmtSigned(d.openPnl), tone: toneFor(d.openPnl) });
  } else missing.push("Open P&L");

  if (d.realizedPnl != null) {
    available.push({ key: "rea", label: "Realized P&L", value: fmtSigned(d.realizedPnl), tone: toneFor(d.realizedPnl) });
  }

  if (d.totalReturnPct != null) {
    available.push({ key: "ret", label: "Total Return", value: fmtPct(d.totalReturnPct), tone: toneFor(d.totalReturnPct) });
  }

  if (d.monthlyPremium != null && d.monthlyPremium > 0) {
    available.push({ key: "prem", label: "Monthly Premium", value: fmtCurrency(d.monthlyPremium, { compact: true }), tone: "good" });
  }

  if (d.activeStrategies != null && d.activeStrategies > 0) {
    available.push({ key: "act", label: "Active Strategies", value: String(d.activeStrategies), tone: "default" });
  }

  if (d.portfolioRiskLabel) {
    const tone: Tone = d.portfolioRiskLabel === "high"
      ? "bad" : d.portfolioRiskLabel === "low" ? "good" : "warn";
    available.push({ key: "risk", label: "Portfolio Risk", value: d.portfolioRiskLabel, tone });
  }

  if (d.cashAvailable != null) {
    available.push({ key: "cash", label: "Cash Available", value: fmtCurrency(d.cashAvailable, { compact: true }), tone: "default" });
  }

  if (d.posture) {
    available.push({ key: "post", label: "AI Posture", value: d.posture, tone: "default", hint: d.freshAt ?? undefined });
  }

  return { available, missing };
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

  const { available, missing } = buildMetrics(data);

  // If literally nothing is wired, show a single setup card
  if (available.length === 0) {
    return (
      <section className="pi-cmdbar pi-cmdbar-setup" data-test="pi-cmdbar">
        <div className="pi-setup-card">
          <span className="pi-setup-eyebrow">Portfolio not connected</span>
          <h3 className="pi-setup-title">Your AI Investing OS is ready</h3>
          <p className="pi-setup-body">
            Connect a paper portfolio or run the recommendation engine to start
            tracking NAV, P&L, premium income, and AI posture in real time.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="pi-cmdbar" data-test="pi-cmdbar">
      {available.map(m => (
        <div key={m.key} className="pi-kpi" data-tone={m.tone}>
          <div className="pi-kpi-label">{m.label}</div>
          <div className="pi-kpi-value">{m.value}</div>
          {m.hint && <div className="pi-kpi-hint">{m.hint}</div>}
        </div>
      ))}
      {missing.length > 0 && available.length < 6 && (
        <div className="pi-kpi-missing" title={missing.join(" · ")}>
          <span className="pi-kpi-missing-label">Not yet tracked</span>
          <span className="pi-kpi-missing-list">{missing.slice(0, 3).join(" · ")}</span>
        </div>
      )}
    </section>
  );
}
