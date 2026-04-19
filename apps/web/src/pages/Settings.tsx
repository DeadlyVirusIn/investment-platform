export default function Settings() {
  return (
    <div>
      <h1 className="page-title">Settings</h1>

      <div className="card max-w-xl">
        <p className="text-text-secondary text-sm mb-4">
          Settings form — TODO Phase 1. Planned options:
        </p>
        <ul className="text-text-muted text-xs space-y-1.5 list-disc list-inside">
          <li>Default currency (USD / EUR / GBP)</li>
          <li>Benchmark index (SPY / QQQ / custom)</li>
          <li>Alert notification channels (email, Telegram, Discord webhook)</li>
          <li>Tiingo API key override (per-session)</li>
          <li>Briefing delivery time &amp; timezone</li>
          <li>Engine config file path (engine.yaml)</li>
          <li>Data retention window</li>
        </ul>
      </div>
    </div>
  );
}
