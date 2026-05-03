// Phase SYSTEM-ALPHA-6 — calibration hooks.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";

export interface CalibrationRec {
  parameter_key: string;
  old_value: number;
  new_value: number;
  reason: string;
  confidence: number;
  sample_size: number;
  metrics: Record<string, unknown>;
  risk_reducing: boolean;
  auto_applicable: boolean;
}

export function useCalibrationRecs() {
  return useQuery<{ count: number; recommendations: CalibrationRec[] }>({
    queryKey: ["alpha", "calibration", "recs"],
    queryFn: () => apiGet("/alpha/calibration/recommendations"),
    staleTime: 5 * 60_000,
  });
}

export function useActiveParams() {
  return useQuery<{ parameters: Record<string, number> }>({
    queryKey: ["alpha", "calibration", "active"],
    queryFn: () => apiGet("/alpha/calibration/active"),
    staleTime: 5 * 60_000,
  });
}

export function useApplyCalibration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (r: CalibrationRec) => apiPost(
      "/alpha/calibration/apply", r,
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "calibration"] });
    },
  });
}

export function useRevertCalibration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (param: string) => apiPost(
      "/alpha/calibration/revert", { parameter_key: param },
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "calibration"] });
    },
  });
}
