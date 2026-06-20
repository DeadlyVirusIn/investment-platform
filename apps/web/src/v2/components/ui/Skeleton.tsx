// Minimal skeleton primitive (investor-demo loading states).
// A neutral pulsing bar used to reserve space and avoid the "0 → real value"
// flash on data-driven cards. No new dependency; pure Tailwind animate-pulse.

export function Skeleton({
  w = '100%',
  h = 12,
  className = '',
  radius = 6,
}: {
  w?: number | string;
  h?: number | string;
  className?: string;
  radius?: number;
}) {
  return (
    <div
      aria-hidden
      className={`animate-pulse ${className}`}
      style={{
        width: typeof w === 'number' ? `${w}px` : w,
        height: typeof h === 'number' ? `${h}px` : h,
        borderRadius: radius,
        background: 'color-mix(in oklab, var(--ink-fainter, #9aa0a6) 18%, transparent)',
      }}
    />
  );
}
