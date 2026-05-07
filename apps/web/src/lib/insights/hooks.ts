// Phase F3 — `useInsight(kind)` lazy hook.
//
// Strict rules:
//   * Does NOT fetch on mount. Caller must invoke `fetchInsight()`
//     from a click handler.
//   * No retries, no polling, no auto-refresh, no localStorage
//     persistence, no in-memory cache across hook instances.
//   * 503 → status="disabled" with no `error` body. The drawer
//     surfaces a calm "insights disabled" copy.
//   * 502 → status="rejected" with `error` carrying the safety
//     reason (already redacted server-side).
//   * Network / unknown HTTP → status="error".
//   * Browsers reject GET-with-body, so the row payload is sent
//     base64url-encoded via `?payload_b64=…` query parameter.
//     Backend (Phase F2 + small F3 extension) decodes it before
//     calling the LLM adapter.

import { useCallback, useState } from "react";

import type {
  InsightKind,
  InsightStatus,
  InsightSuccess,
} from "./types";


// ---------------------------------------------------------------------
// base64url helper (browser-safe; no deps)
// ---------------------------------------------------------------------

function encodePayloadB64(payload: unknown): string {
  const json = JSON.stringify(payload);
  const utf8 = new TextEncoder().encode(json);
  let binary = "";
  utf8.forEach((b) => { binary += String.fromCharCode(b); });
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}


// ---------------------------------------------------------------------
// Public hook
// ---------------------------------------------------------------------

export interface UseInsightResult {
  /** Trigger a single fetch. Pass the kind's payload (or undefined
   *  to use the server-side fixture). MUST be called from a user
   *  gesture (button click) — never from `useEffect`. */
  fetchInsight: (payload?: unknown) => Promise<void>;

  /** Latest successful response, or null when not ready. */
  data: InsightSuccess | null;

  /** Discrete state machine. See `InsightStatus`. */
  status: InsightStatus;

  /** Convenience boolean — equivalent to `status === "loading"`. */
  loading: boolean;

  /** Human-readable error string for the "rejected" / "error"
   *  states. Always null when `status` is "ready" or "disabled". */
  error: string | null;

  /** Clear all hook state and return to "idle". */
  reset: () => void;
}


export function useInsight(kind: InsightKind): UseInsightResult {
  const [data, setData] = useState<InsightSuccess | null>(null);
  const [status, setStatus] = useState<InsightStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setData(null);
    setStatus("idle");
    setError(null);
  }, []);

  const fetchInsight = useCallback(
    async (payload?: unknown): Promise<void> => {
      setStatus("loading");
      setError(null);
      setData(null);

      // Build the URL. Browsers reject GET-with-body, so we serialize
      // the payload as a base64url query parameter when present.
      let url = `/api/insights/${kind}`;
      if (payload !== undefined && payload !== null) {
        url += `?payload_b64=${encodePayloadB64(payload)}`;
      }

      let res: Response;
      try {
        res = await fetch(url, {
          method: "GET",
          headers: { Accept: "application/json" },
        });
      } catch (e) {
        // Network failure — DOM TypeError, AbortError, etc. NEVER
        // retry from the hook; the operator must click again.
        setStatus("error");
        setError(e instanceof Error ? e.message : "network error");
        return;
      }

      // Best-effort body decode — error envelopes are always JSON.
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        body = null;
      }

      if (res.status === 503) {
        setStatus("disabled");
        return;
      }
      if (res.status === 502) {
        setStatus("rejected");
        const reason =
          (body && typeof body === "object" && "reason" in body
            && typeof (body as { reason: unknown }).reason === "string")
            ? (body as { reason: string }).reason
            : "rejected by safety layer";
        setError(reason);
        return;
      }
      if (!res.ok) {
        setStatus("error");
        const detail =
          (body && typeof body === "object" && "error" in body
            && typeof (body as { error: unknown }).error === "string")
            ? (body as { error: string }).error
            : `HTTP ${res.status}`;
        setError(detail);
        return;
      }

      // 200 OK — body must conform to InsightSuccess.
      setData(body as InsightSuccess);
      setStatus("ready");
    },
    [kind],
  );

  return {
    fetchInsight,
    data,
    status,
    loading: status === "loading",
    error,
    reset,
  };
}
