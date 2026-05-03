import type { ReactNode } from 'react';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-10">
      <span className="text-text-muted text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({
  title = 'Nothing here yet',
  hint,
}: {
  title?: string;
  hint?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <p className="text-text-secondary text-sm">{title}</p>
      {hint && <p className="text-text-muted text-xs mt-1 max-w-sm">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <p className="text-danger text-sm">Error</p>
      <p className="text-text-muted text-xs mt-1 max-w-md break-all">{message}</p>
    </div>
  );
}
