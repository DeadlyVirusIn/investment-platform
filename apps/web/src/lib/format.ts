// Deterministic formatters. All take string-or-null inputs (backend sends
// Decimals as strings). Return plain strings ready to paint into the DOM.

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

const NUM = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

const PCT = new Intl.NumberFormat('en-US', {
  style: 'percent',
  maximumFractionDigits: 2,
});

export function n(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null;
  const parsed = typeof v === 'number' ? v : parseFloat(v);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatCurrency(v: string | number | null | undefined, fallback = '—'): string {
  const parsed = n(v);
  return parsed === null ? fallback : USD.format(parsed);
}

export function formatSignedCurrency(v: string | number | null | undefined, fallback = '—'): string {
  const parsed = n(v);
  if (parsed === null) return fallback;
  const sign = parsed > 0 ? '+' : '';
  return sign + USD.format(parsed);
}

export function formatNumber(
  v: string | number | null | undefined,
  maxDigits = 4,
  fallback = '—',
): string {
  const parsed = n(v);
  if (parsed === null) return fallback;
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: maxDigits,
  }).format(parsed);
}

export function formatPercent(
  v: string | number | null | undefined,
  fallback = '—',
): string {
  const parsed = n(v);
  if (parsed === null) return fallback;
  // Treat input as a raw fraction (0.1234 → 12.34%)
  return PCT.format(parsed);
}

export function formatSignedPercent(
  v: string | number | null | undefined,
  fallback = '—',
): string {
  const parsed = n(v);
  if (parsed === null) return fallback;
  const sign = parsed > 0 ? '+' : '';
  return sign + PCT.format(parsed);
}

export function formatRatio(
  v: string | number | null | undefined,
  digits = 2,
  fallback = '—',
): string {
  const parsed = n(v);
  if (parsed === null) return fallback;
  return parsed.toFixed(digits);
}

export function formatInt(v: number | null | undefined, fallback = '—'): string {
  if (v === null || v === undefined) return fallback;
  return NUM.format(v);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelative(iso: string | number | Date | null | undefined): string {
  if (iso === null || iso === undefined) return '—';
  const d = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return 'now';
  const secs = Math.floor(diffMs / 1000);
  if (secs < 45) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

// Semantic helpers for deciding color class from numeric sign.
export function pnlToneClass(v: string | number | null | undefined): string {
  const parsed = n(v);
  if (parsed === null) return 'text-text-muted';
  if (parsed > 0) return 'text-success';
  if (parsed < 0) return 'text-danger';
  return 'text-text-secondary';
}
