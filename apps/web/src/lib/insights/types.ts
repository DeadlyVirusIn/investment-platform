// Phase F3 — Insight Drawer types.
//
// Mirrors the read-only shape returned by GET /api/insights/{kind}
// and the two error envelopes (HTTP 503 and HTTP 502). NEVER models
// fields that the backend does not emit; NEVER models trading or
// execution actions — the drawer is research context only.

export type InsightKind =
  | "trade_quality"
  | "risk_commentary"
  | "exit_review"
  | "options_thesis";


// Literal banner string. Source of truth lives on the server
// (`agents.registry.BANNER`). Re-stating the literal here keeps the
// drawer's banner row authoritative even if the network returns a
// truncated body — the drawer never trusts a missing banner.
export const INSIGHT_BANNER =
  "AI research insight — not execution logic.";


export interface InsightSuccess {
  kind: InsightKind;
  model: string;
  generated_at: string;
  banner: string;
  content_markdown: string;
  source_endpoint: string;
  llm_enabled: true;
}


export interface InsightDisabledBody {
  error: "agent insights disabled";
}


export interface InsightUnsafeBody {
  error: "insight rejected by safety layer";
  reason?: string;
}


// Drawer state machine. Discrete states keep the drawer's branching
// readable and prevent rendering mixed states (e.g., spinner + body).
export type InsightStatus =
  | "idle"        // hook never triggered; drawer not open
  | "loading"     // request in flight
  | "ready"       // 200 received, content available
  | "disabled"    // 503 — flag off or key missing
  | "rejected"    // 502 — safety layer rejected the LLM body
  | "error";      // network failure or non-handled HTTP code


// User-friendly labels per kind. Used by the drawer header and by
// any mounting card that wants to title its trigger button.
export const KIND_LABEL: Record<InsightKind, string> = {
  trade_quality: "Trade Quality",
  risk_commentary: "Risk Commentary",
  exit_review: "Exit Review",
  options_thesis: "Options Thesis",
};
