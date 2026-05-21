// Phase L UI-1 — reasoning API client.
//
// fetchEnvelope(paperTradeId): returns the rendered envelope OR null on 404.
// 404 is the system's HONEST ABSENCE signal — the caller MUST handle it,
// must not fabricate a substitute.

import type { ReasoningResponse } from "./types";

const BASE = "/api";

export class ReasoningFetchError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/**
 * Fetch the deterministic reasoning envelope for a paper trade.
 *
 *   - Returns the response on 200.
 *   - Returns null on 404 — caller must show the honest-absence state.
 *   - Throws ReasoningFetchError on any other non-2xx — caller decides
 *     whether to retry or surface an error message.
 *
 * The function performs ZERO transformation of the response payload.
 * Every visible field is server-rendered.
 */
export async function fetchEnvelope(
  paperTradeId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<ReasoningResponse | null> {
  if (!paperTradeId) {
    return null;
  }
  const url = `${BASE}/v2/decisions/${encodeURIComponent(paperTradeId)}/reasoning`;
  const resp = await fetch(url, {
    signal: opts.signal,
    credentials: "same-origin",
  });
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new ReasoningFetchError(
      `reasoning fetch failed: ${resp.status} ${resp.statusText}`,
      resp.status,
    );
  }
  return (await resp.json()) as ReasoningResponse;
}
