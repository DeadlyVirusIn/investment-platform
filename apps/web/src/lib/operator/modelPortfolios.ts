// MVP — model-portfolio data hooks. Reuse the shared apiGet + react-query.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface ModelPortfolioSummary {
  slug: string;
  name: string;
  thesis: string | null;
  risk_label: string | null;
  holdings_count: number;
  return_pct: number | null;
  max_drawdown_pct: number | null;
  since: string | null;
  points: number;
  spark: number[];
}

export interface ModelPortfolioDetail {
  slug: string;
  name: string;
  thesis: string | null;
  risk_label: string | null;
  holdings: { symbol: string; weight_pct: number }[];
  return_pct: number | null;
  max_drawdown_pct: number | null;
  since: string | null;
  points: number;
  curve: { d: string; nav: number }[];
}

export function useModelPortfolios() {
  return useQuery<{ portfolios: ModelPortfolioSummary[] }>({
    queryKey: ["model-portfolios"],
    queryFn: () => apiGet<{ portfolios: ModelPortfolioSummary[] }>("/model-portfolios"),
    staleTime: 300_000,
  });
}

export function useModelPortfolio(slug: string | undefined) {
  return useQuery<ModelPortfolioDetail>({
    queryKey: ["model-portfolio", slug],
    queryFn: () => apiGet<ModelPortfolioDetail>(`/model-portfolios/${slug}`),
    enabled: !!slug,
    staleTime: 300_000,
  });
}
