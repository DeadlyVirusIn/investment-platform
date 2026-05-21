// Phase L UI-1 — React hook around fetchEnvelope.
//
// Minimal local-state hook (no react-query dep assumed) — same pattern
// as other lib/* hooks. Handles loading + null (404) + error states
// without ever fabricating a substitute envelope.

import { useEffect, useRef, useState } from "react";

import { fetchEnvelope, ReasoningFetchError } from "./api";
import type { ReasoningResponse } from "./types";

export interface UseEnvelopeState {
  /** True on the first request only. */
  loading: boolean;
  /** Set on 200. Null on 404 (honest absence). */
  envelope: ReasoningResponse | null;
  /** Error for non-2xx-non-404 responses. */
  error: ReasoningFetchError | null;
}

export function useEnvelope(paperTradeId: string | null | undefined): UseEnvelopeState {
  const [state, setState] = useState<UseEnvelopeState>({
    loading: !!paperTradeId,
    envelope: null,
    error: null,
  });
  // Track latest request to ignore stale responses.
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (!paperTradeId) {
      setState({ loading: false, envelope: null, error: null });
      return;
    }
    const myId = ++reqIdRef.current;
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));

    fetchEnvelope(paperTradeId, { signal: controller.signal })
      .then((env) => {
        if (myId !== reqIdRef.current) return;
        setState({ loading: false, envelope: env, error: null });
      })
      .catch((err) => {
        if (myId !== reqIdRef.current) return;
        if (err?.name === "AbortError") return;
        const errOut =
          err instanceof ReasoningFetchError
            ? err
            : new ReasoningFetchError(String(err), 0);
        setState({ loading: false, envelope: null, error: errOut });
      });

    return () => controller.abort();
  }, [paperTradeId]);

  return state;
}
