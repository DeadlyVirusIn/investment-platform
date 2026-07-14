// companyMeta — humanize engine-coded asset metadata for beginner surfaces.
//
// The engine stores sector as a short code ("consumer_disc"). Beginners must
// NEVER see the raw code. sectorLabel maps the known codes to plain English;
// unknown/missing codes return null so the caller hides the chip rather than
// showing a code. No fabrication.
//
// NOTE (Phase 2/3, see docs/ops/COMPANY_METADATA_BACKFILL.md): company NAME
// and DESCRIPTION are not available yet (asset.name is NULL for all rows; no
// description column). Until the Polygon ticker-details backfill lands, the
// UI shows the ticker alone — it does not invent a name or description.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface AssetRow { symbol: string | null; name: string | null }

// Symbol → company-name map for surfaces whose payload carries only a ticker
// (Watchlist, Paper Book, Track Record, portfolio holdings). One cached
// /assets fetch; names come from the Polygon backfill (asset.name). Missing
// names are simply absent → CompanyTitle falls back to the ticker.
export function useAssetNames(): Record<string, string> {
  const { data } = useQuery<Record<string, string>>({
    queryKey: ['assets', 'names'],
    queryFn: async () => {
      const r = await apiGet<{ assets: AssetRow[] }>('/assets?limit=5000');
      const m: Record<string, string> = {};
      for (const a of r.assets ?? []) {
        if (a.symbol && a.name) m[a.symbol.toUpperCase()] = a.name;
      }
      return m;
    },
    staleTime: 3_600_000,            // names change rarely
    refetchOnWindowFocus: false,
  });
  return data ?? {};
}

const SECTOR_LABELS: Record<string, string> = {
  tech: 'Technology',
  consumer_disc: 'Consumer Discretionary',
  consumer_stap: 'Consumer Staples',
  communication: 'Communication Services',
  real_estate: 'Real Estate',
  financials: 'Financials',
  healthcare: 'Healthcare',
  industrials: 'Industrials',
  materials: 'Materials',
  energy: 'Energy',
  utilities: 'Utilities',
  etf: 'ETF',
};

/** Plain-English sector, or null when unknown/missing (caller hides the chip). */
export function sectorLabel(code?: string | null): string | null {
  if (!code) return null;
  return SECTOR_LABELS[code.trim().toLowerCase()] ?? null;
}

// Trim verbose legal/share-class suffixes from a provider company name for
// beginner display ("Royalty Pharma plc Class A Ordinary Shares" →
// "Royalty Pharma"). Display-only cleanup — not fabrication; the underlying
// stored name is unchanged. Conservative: leaves "Group"/"Holdings" intact.
export function cleanCompanyName(raw?: string | null): string | null {
  if (!raw) return null;
  let s = raw.trim();
  s = s.replace(/\s+(class\s+[a-z]\s+)?(ordinary|common)\s+(shares?|stock)$/i, '');
  s = s.replace(/\s+american\s+depositary\s+shares?.*$/i, '');
  s = s.replace(/\s+class\s+[a-z]$/i, '');
  s = s.replace(/,?\s+(inc|corp|corporation|co|ltd|plc|llc|l\.?p|s\.?a|n\.?v|a\.?g)\.?$/i, '');
  return s.trim() || raw.trim();
}
