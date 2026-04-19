import { useState } from 'react';

type InputMethod = 'manual' | 'csv' | 'api' | 'wallet';

const INPUT_METHODS: { id: InputMethod; label: string; desc: string }[] = [
  {
    id: 'manual',
    label: 'Manual Entry',
    desc: 'Add transactions one by one. Best for small portfolios or one-off corrections.',
  },
  {
    id: 'csv',
    label: 'CSV Import',
    desc: 'Upload a CSV export from your broker (Schwab, Fidelity, IBKR format supported).',
  },
  {
    id: 'api',
    label: 'Broker API',
    desc: 'Connect via read-only API key. Supported: Alpaca, IBKR (planned).',
  },
  {
    id: 'wallet',
    label: 'Crypto Wallet',
    desc: 'Enter a public wallet address — on-chain history is fetched automatically.',
  },
];

export default function PortfolioSetup() {
  const [selected, setSelected] = useState<InputMethod>('manual');

  return (
    <div>
      <h1 className="page-title">Portfolio Setup</h1>

      <p className="text-text-secondary text-sm mb-6 max-w-prose">
        Choose how you'd like to populate your portfolio. All methods feed into
        the same ledger model (transaction → lot → position snapshot). You can
        mix methods — e.g. CSV for historical data plus Manual for recent buys.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl mb-8">
        {INPUT_METHODS.map(({ id, label, desc }) => (
          <button
            key={id}
            onClick={() => setSelected(id)}
            className={[
              'card text-left transition-all',
              selected === id
                ? 'border-accent ring-1 ring-accent'
                : 'hover:border-surface-hover',
            ].join(' ')}
          >
            <p className="text-sm font-medium text-text-primary mb-1">
              {label}
            </p>
            <p className="text-xs text-text-secondary">{desc}</p>
          </button>
        ))}
      </div>

      <div className="card max-w-2xl">
        <p className="text-sm font-medium text-text-primary mb-2">
          Selected: {INPUT_METHODS.find((m) => m.id === selected)?.label}
        </p>
        <p className="text-xs text-text-muted">
          Form implementation — TODO in Phase 1.
        </p>
      </div>
    </div>
  );
}
