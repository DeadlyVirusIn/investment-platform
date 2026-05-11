// FetchError — visible error UI for failed page-level fetches.
// Used by useFetchWithError consumers. Honest failure state, not a
// disguised empty.

export interface FetchErrorProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}


export default function FetchError({
  title = "Could not load data",
  message,
  onRetry,
}: FetchErrorProps) {
  return (
    <div className="fetch-error" role="alert" data-test="fetch-error">
      <div className="fetch-error-eyebrow">Backend error</div>
      <h3 className="fetch-error-title">{title}</h3>
      {message && <p className="fetch-error-message">{message}</p>}
      <p className="fetch-error-hint">
        The data layer reported an error. The page is empty because the
        request failed — this is not a "no data today" state.
      </p>
      {onRetry && (
        <button type="button" className="fetch-error-retry" onClick={onRetry}>
          Retry →
        </button>
      )}
    </div>
  );
}
