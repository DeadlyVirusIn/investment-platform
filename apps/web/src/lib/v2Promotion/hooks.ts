import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";


export type V2PromotionState =
  | "NOT_READY"
  | "SUSPENDED"
  | "WATCH"
  | "READY_FOR_REVIEW"
  | "STRONG_CANDIDATE"
  | "APPROVED_FOR_SHADOW_REPLACEMENT";


export interface SnapshotSummary {
  snapshot_id: number;
  as_of_date: string;
  iso_year: number;
  iso_week: number;
  state: V2PromotionState;
  prior_state: V2PromotionState | null;
  promotion_confidence: number;
  verdict_streak: number;
  readiness_streak: number;
  rollback_reason: string | null;
  comparison_verdict: string | null;
  comparison_readiness: string | null;
  comparison_confidence: number | null;
  tail_guard_triggered: boolean;
  n_divergent_days: number | null;
  edge_bps: number | null;
  impact_weighted_edge: number | null;
  comparison_fetch_ok: boolean;
  created_at: string;
  // Phase 9A — governance hardening metadata
  snapshot_content_hash: string | null;
  schema_version: number;
  code_version: string | null;
  evaluated_at_utc: string | null;
  timezone: string | null;
  days_until_approval_expiry: number | null;
  approval_expiry_warning: boolean;
}


export interface ApprovalRow {
  id: number;
  snapshot_id: number;
  decision: "APPROVE" | "RESCIND" | "RESUME_FROM_SUSPENDED";
  approver: string;
  rationale: string;
  approved_at: string;
}


export interface StateResponse {
  snapshot: SnapshotSummary | null;
  approvals: ApprovalRow[];
  gates_passing?: Record<string, boolean>;
  approver_allowlist_size: number;
  note?: string;
}


export interface SnapshotsResponse {
  weeks_requested: number;
  n_returned: number;
  snapshots: SnapshotSummary[];
}


export interface GateDetail {
  name: string;
  passed: boolean;
  reason: string;
  details: Record<string, unknown>;
}


export interface ConfidenceBreakdown {
  sample: number;
  verdict_streak: number;
  readiness_streak: number;
  edge: number;
  tail: number;
  regime: number;
  stability: number;
  total: number;
}


export interface GatesResponse {
  snapshot_id: number;
  as_of_date: string;
  iso_year: number;
  iso_week: number;
  state: V2PromotionState;
  promotion_confidence: number;
  gates: Record<string, GateDetail>;
  confidence_breakdown: ConfidenceBreakdown | Record<string, never>;
  decision: { new_state?: string; notes?: string[]; rollback_reason?: string | null };
  streaks: { verdict_streak: number; readiness_streak: number };
  comparison_fetch_ok: boolean;
}


// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useV2PromotionState() {
  return useQuery<StateResponse>({
    queryKey: ["v2Promotion.state"],
    queryFn: () => apiGet<StateResponse>("/v2-promotion/state"),
    staleTime: 60_000,
  });
}


export function useV2PromotionSnapshots(weeks = 12) {
  return useQuery<SnapshotsResponse>({
    queryKey: ["v2Promotion.snapshots", weeks],
    queryFn: () =>
      apiGet<SnapshotsResponse>(`/v2-promotion/snapshots?weeks=${weeks}`),
    staleTime: 60_000,
  });
}


export function useV2PromotionGates(snapshotId?: number) {
  const path = snapshotId
    ? `/v2-promotion/gates?snapshot_id=${snapshotId}`
    : `/v2-promotion/gates`;
  return useQuery<GatesResponse>({
    queryKey: ["v2Promotion.gates", snapshotId ?? "latest"],
    queryFn: () => apiGet<GatesResponse>(path),
    staleTime: 60_000,
  });
}


// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export interface ApproveBody {
  snapshot_id: number;
  approver: string;
  rationale: string;
}


export interface ApproveResponse {
  status: "inserted";
  approval: ApprovalRow;
  snapshot_id: number;
  snapshot_state_at_approval: V2PromotionState;
  note: string;
}


export function useV2PromotionApprove() {
  const qc = useQueryClient();
  return useMutation<ApproveResponse, Error, ApproveBody>({
    mutationFn: (body) =>
      apiPost<ApproveResponse>("/v2-promotion/approve", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["v2Promotion.state"] });
      qc.invalidateQueries({ queryKey: ["v2Promotion.gates"] });
    },
  });
}


export interface RescindBody {
  snapshot_id: number;
  approver: string;
  rationale: string;
}


export interface RescindResponse {
  status: "inserted";
  rescission: ApprovalRow;
  rescinded_snapshot_id: number;
  latest_snapshot_state: V2PromotionState;
  note: string;
}


export function useV2PromotionRescind() {
  const qc = useQueryClient();
  return useMutation<RescindResponse, Error, RescindBody>({
    mutationFn: (body) =>
      apiPost<RescindResponse>("/v2-promotion/rescind", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["v2Promotion.state"] });
      qc.invalidateQueries({ queryKey: ["v2Promotion.gates"] });
    },
  });
}


// Phase 9A — RESUME_FROM_SUSPENDED operator action

export interface ResumeBody {
  snapshot_id: number;
  approver: string;
  rationale: string;
}


export interface ResumeResponse {
  status: "inserted";
  resume: ApprovalRow;
  snapshot_id: number;
  snapshot_state_at_resume_request: V2PromotionState;
  note: string;
}


export function useV2PromotionResume() {
  const qc = useQueryClient();
  return useMutation<ResumeResponse, Error, ResumeBody>({
    mutationFn: (body) =>
      apiPost<ResumeResponse>("/v2-promotion/resume-from-suspended", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["v2Promotion.state"] });
      qc.invalidateQueries({ queryKey: ["v2Promotion.gates"] });
    },
  });
}
