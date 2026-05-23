// AcademyChips — small sage-light pills for taxonomy tags.
//
// Phase A visual-parity primitive. Logic-free.

export function AcademyChips({
  academies,
  className,
}: {
  academies: readonly string[];
  className?: string;
}) {
  if (academies.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-1.5 ${className ?? ''}`}>
      {academies.map((a) => (
        <span
          key={a}
          className="px-2 py-0.5 rounded-full text-[10.5px] font-semibold"
          style={{
            backgroundColor: 'var(--sage-light)',
            color: 'var(--muted-foreground)',
          }}
        >
          {a}
        </span>
      ))}
    </div>
  );
}
