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
