import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface Column<T> {
  key: string;
  label: ReactNode;
  render: (row: T) => ReactNode;
  align?: 'left' | 'right' | 'center';
  /** CSS width (e.g. "120px" or "20%"). */
  width?: string;
  className?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyLabel?: string;
  compact?: boolean;
}

const ALIGN = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

export default function Table<T>({
  columns,
  rows,
  rowKey,
  emptyLabel = 'No data',
  compact = false,
}: TableProps<T>) {
  if (rows.length === 0) {
    return (
      <div className="text-sm text-text-muted py-6 text-center">{emptyLabel}</div>
    );
  }

  const cellPad = compact ? 'px-3 py-2' : 'px-4 py-2.5';

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-border">
            {columns.map(col => (
              <th
                key={col.key}
                className={cn(
                  cellPad,
                  ALIGN[col.align ?? 'left'],
                  'text-[11px] font-semibold tracking-wider uppercase text-text-muted',
                )}
                style={col.width ? { width: col.width } : undefined}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr
              key={rowKey(row)}
              className="border-b border-surface-border/60 hover:bg-surface-hover/40 transition-colors"
            >
              {columns.map(col => (
                <td
                  key={col.key}
                  className={cn(
                    cellPad,
                    ALIGN[col.align ?? 'left'],
                    col.align === 'right' && 'font-mono tabular-nums',
                    col.className,
                  )}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
