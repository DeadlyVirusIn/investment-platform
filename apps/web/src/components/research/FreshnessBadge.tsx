// Phase 11W (Phase F) — neutral freshness badge for research
// artifacts. Shows age vs the user-specified "now" reference. NEVER
// uses green/red coloring (those are reserved for action surfaces).
// Three buckets: fresh / aging / stale — all rendered in
// neutral grey-yellow tones.

export interface FreshnessBadgeProps {
  isoTimestamp?: string | null;
  nowOverride?: Date;             // for tests
  freshHours?: number;            // default 6h
  agingHours?: number;            // default 24h
}

function _hoursAgo(iso: string, now: Date): number {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return Number.POSITIVE_INFINITY;
  return (now.getTime() - then) / 3_600_000;
}

export default function FreshnessBadge(props: FreshnessBadgeProps) {
  const now = props.nowOverride ?? new Date();
  const fresh = props.freshHours ?? 6;
  const aging = props.agingHours ?? 24;
  if (!props.isoTimestamp) {
    return (
      <span
        className="research-freshness research-freshness-unknown"
        data-bucket="unknown"
        style={{
          background: '#eeeeee',
          color: '#757575',
          fontSize: 11,
          padding: '2px 6px',
          borderRadius: 3,
        }}
      >
        no-timestamp
      </span>
    );
  }
  const h = _hoursAgo(props.isoTimestamp, now);
  let bucket = 'fresh';
  let bg = '#fffde7';
  let fg = '#827717';
  let label = `${h.toFixed(1)}h`;
  if (h >= aging) {
    bucket = 'stale';
    bg = '#fafafa';
    fg = '#9e9e9e';
    label = `${h.toFixed(0)}h (stale)`;
  } else if (h >= fresh) {
    bucket = 'aging';
    bg = '#fff8e1';
    fg = '#bf6f00';
    label = `${h.toFixed(0)}h`;
  }
  return (
    <span
      className={`research-freshness research-freshness-${bucket}`}
      data-bucket={bucket}
      title={props.isoTimestamp}
      style={{
        background: bg,
        color: fg,
        fontSize: 11,
        padding: '2px 6px',
        borderRadius: 3,
      }}
    >
      {label}
    </span>
  );
}
