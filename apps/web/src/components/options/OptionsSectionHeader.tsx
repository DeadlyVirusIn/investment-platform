// Phase 11L — Section header used to group page surfaces.
// Visual-only structure. Subtle uppercase label + optional caption.

export default function OptionsSectionHeader({
  title, caption, right,
}: {
  title: string;
  caption?: string;
  right?: React.ReactNode;
}) {
  return (
    <header className="mt-2 mb-2 flex items-baseline justify-between gap-3">
      <div>
        <h2
          className="text-[11px] font-semibold uppercase tracking-[0.14em]"
          style={{ color: 'var(--color-muted)' }}
        >
          {title}
        </h2>
        {caption ? (
          <p className="mt-0.5 text-[11px] text-zinc-500">{caption}</p>
        ) : null}
      </div>
      {right ? <div>{right}</div> : null}
    </header>
  );
}
