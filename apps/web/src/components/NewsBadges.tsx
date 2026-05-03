import Badge from '@/components/Badge';
import type { NewsSymbolSummary } from '@/types';

function sentimentTone(label: string): 'positive' | 'negative' | 'muted' | 'info' {
  if (label === 'positive') return 'positive';
  if (label === 'negative') return 'negative';
  if (label === 'neutral') return 'info';
  return 'muted';
}

function categoryLabel(c: string | null): string {
  if (!c) return '—';
  return c.charAt(0).toUpperCase() + c.slice(1);
}

/** Compact badges for a symbol-level news summary. Use inline on rec rows. */
export function NewsSummaryBadges({
  summary,
}: {
  summary: NewsSymbolSummary | null | undefined;
}) {
  if (!summary || summary.article_count === 0) {
    return <span className="text-xs text-text-muted">no recent news</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      <Badge tone={sentimentTone(summary.sentiment_label)}>
        {summary.sentiment_label}
      </Badge>
      {summary.dominant_category && (
        <Badge tone="muted">{categoryLabel(summary.dominant_category)}</Badge>
      )}
      {summary.max_impact_score >= 3 && (
        <Badge tone="warning">high impact</Badge>
      )}
      <span className="text-xs text-text-muted">
        {summary.article_count} article{summary.article_count === 1 ? '' : 's'}
      </span>
    </div>
  );
}

/** Single-headline compact line with sentiment color. */
export function NewsHeadline({
  title,
  url,
  sentiment,
}: {
  title: string;
  url: string;
  sentiment: string;
}) {
  const cls =
    sentiment === 'positive'
      ? 'text-success'
      : sentiment === 'negative'
      ? 'text-danger'
      : 'text-text-secondary';
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`block text-xs hover:underline truncate ${cls}`}
      title={title}
    >
      {title}
    </a>
  );
}
