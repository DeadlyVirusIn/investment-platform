// Phase 13b — shared fetch hook with explicit error state.
//
// Replaces the silent `try { ... } catch { setLoading(false) }`
// pattern that 4 narrative pages used. Without this hook, a
// backend 500 was indistinguishable from a genuine empty day —
// the calm empty state implicitly signaled "system is healthy"
// when in fact the request had failed.
//
// All four octo-debate panelists flagged this as a fakes-by-
// omission violation. See docs/ux/octo_phase_12_review.md.

import { useEffect, useState } from "react";


export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}


/**
 * Wrap an async fetch in a hook that surfaces error state.
 *
 * @param fetchFn  Async function returning T. Re-runs when `deps` change.
 * @param deps     Dependency array (mirrors useEffect deps semantics).
 *
 * @example
 *   const { data, loading, error } = useFetchWithError(
 *     () => fetchPicks(30),
 *     []
 *   );
 *   if (error) return <FetchError message={error.message} />;
 *   if (loading) return <Spinner />;
 *   return <Grid picks={data!} />;
 */
export function useFetchWithError<T>(
  fetchFn: () => Promise<T>,
  deps: ReadonlyArray<unknown>,
): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchFn()
      .then(d => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      })
      .catch(err => {
        if (cancelled) return;
        const wrapped = err instanceof Error ? err : new Error(String(err));
        setError(wrapped);
        setLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error };
}
