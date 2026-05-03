// Phase SYSTEM-ALPHA-3 — rule suggestion hooks.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";

export interface RuleSuggestion {
  id: string;
  rule_id: string;
  rule_type: string;
  target: string;
  description: string;
  confidence: number;
  sample_size: number;
  expected_impact: string;
  risk_level: "low" | "medium" | "high";
  auto_applicable: boolean;
  parameters: Record<string, unknown>;
  status: string;
  created_at: string;
}

export function useRuleSuggestions(status = "pending") {
  return useQuery<{ count: number; suggestions: RuleSuggestion[] }>({
    queryKey: ["alpha", "rules", "suggestions", status],
    queryFn: () => apiGet(
      `/alpha/rules/suggestions?status=${status}&limit=20`,
    ),
    staleTime: 5 * 60_000,
  });
}

export function useActiveRules() {
  return useQuery<{ count: number; rules: any[] }>({
    queryKey: ["alpha", "rules", "active"],
    queryFn: () => apiGet("/alpha/rules/active"),
    staleTime: 5 * 60_000,
  });
}

export function useApplySuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { suggestion_id: string; force?: boolean }) =>
      apiPost("/alpha/rules/apply", {
        suggestion_id: vars.suggestion_id,
        force_manual: vars.force ?? false,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "rules"] });
    },
  });
}

export function useIgnoreSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { suggestion_id: string; reason?: string }) =>
      apiPost("/alpha/rules/ignore", vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "rules"] });
    },
  });
}

export function useRollbackRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { rule_id: string; reason?: string }) =>
      apiPost("/alpha/rules/rollback", vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "rules"] });
    },
  });
}
