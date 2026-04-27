// Phase 11F — Options-specific formatters.
// Critical rule: NULL is NEVER converted to 0.
// Caller decides whether NULL means "Insufficient data" or "Unavailable"
// via the `nullText` argument.

export function fmtMoney(
  v: string | number | null | undefined,
  opts: { digits?: number; nullText?: string; suffix?: string } = {},
): string {
  const { digits = 2, nullText = 'Unavailable', suffix = '' } = opts;
  if (v === null || v === undefined || v === '') return nullText;
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n)) return nullText;
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(digits)}${suffix}`;
}

export function fmtPct(
  v: string | number | null | undefined,
  opts: { digits?: number; nullText?: string } = {},
): string {
  const { digits = 2, nullText = 'Insufficient data' } = opts;
  if (v === null || v === undefined || v === '') return nullText;
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n)) return nullText;
  return `${(n * 100).toFixed(digits)}%`;
}

export function fmtRaw(
  v: string | number | null | undefined,
  opts: { digits?: number; nullText?: string } = {},
): string {
  const { digits = 4, nullText = 'Unavailable' } = opts;
  if (v === null || v === undefined || v === '') return nullText;
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n)) return nullText;
  return n.toFixed(digits);
}

export function fmtInt(
  v: number | null | undefined,
  opts: { nullText?: string } = {},
): string {
  const { nullText = 'Unavailable' } = opts;
  if (v === null || v === undefined) return nullText;
  return String(v);
}

export function fmtTimestamp(iso: string | null | undefined): string {
  if (!iso) return 'Unavailable';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
