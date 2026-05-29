// Canonical-portfolio consistency gate (Phase A/B).
//
// User-facing V2 routes must read the canonical stock portfolio
// (useCanonicalStockPortfolio → /paper/canonical/stock) — never the
// legacy localStorage PaperBook store, and never an aggregate
// "all active portfolios" summary for headline portfolio numbers.
//
// Fails (exit 1) if a forbidden pattern appears in apps/web/src/v2.
// Allowed exceptions: the PaperBook store file itself (removed in
// Phase C) and this script.
//
// Run: node scripts/lint-canonical-portfolio.mjs

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SCAN_DIR = join(ROOT, 'src', 'v2');

// Files exempt from the gate.
//   - the store file itself (deleted in Phase C);
//   - KNOWN PENDING consumers of the local sandbox book (interactive
//     features: trade sheet, hero, onboarding progress). Phase C MUST
//     migrate these and SHRINK THIS LIST TO EMPTY. No NEW file may be
//     added here.
const EXEMPT = [
  join('src', 'v2', 'state', 'PaperBook.tsx'),
  // PaperBookProvider wiring — removed in Phase C once consumers below migrate.
  join('src', 'v2', 'V2App.tsx'),
  // --- Phase C debt (migrate + remove) ---
  join('src', 'v2', 'components', 'ArthHeroCard.tsx'),
  join('src', 'v2', 'components', 'DecisionDeskHero.tsx'),
  join('src', 'v2', 'components', 'FirstPositionPanel.tsx'),
  join('src', 'v2', 'components', 'TradeSheet.tsx'),
  join('src', 'v2', 'pages', 'MePage.tsx'),
  join('src', 'v2', 'pages', 'ReflectionsReview.tsx'),
  join('src', 'v2', 'pages', 'StartHere.tsx'),
  join('src', 'v2', 'pages', 'TryFromLesson.tsx'),
];

// pattern → human reason
const FORBIDDEN = [
  [/\busePaperBook\b/, 'usePaperBook (local sandbox store) — use useCanonicalStockPortfolio'],
  [/from ['"][^'"]*state\/PaperBook['"]/, "import from state/PaperBook — use canonical backend hooks"],
  [/\busePaperSummary\b/, 'usePaperSummary (aggregate of ALL active portfolios) — use useCanonicalStockPortfolio for portfolio NAV'],
];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (/\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

let violations = 0;
for (const file of walk(SCAN_DIR)) {
  const rel = relative(ROOT, file).split(sep).join('/');
  if (EXEMPT.some((e) => rel.endsWith(e.split(sep).join('/')))) continue;
  const text = readFileSync(file, 'utf8');
  text.split('\n').forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')) return;
    for (const [re, reason] of FORBIDDEN) {
      if (re.test(line)) {
        console.error(`✖ ${rel}:${i + 1}  ${reason}`);
        console.error(`    ${line.trim()}`);
        violations++;
      }
    }
  });
}

// ---------------------------------------------------------------------------
// P0 live-recommendation routes — must be 100% live, NO static recommendation
// literals. These three were rewired in the P0 live-recommendation pass and
// must never regress to TODAYS_DESK / generateBriefing / arthosData recs.
// ---------------------------------------------------------------------------
const P0_ROUTES = [
  join('src', 'v2', 'pages', 'Briefing.tsx'),
  join('src', 'v2', 'pages', 'Opportunities.tsx'),
  join('src', 'v2', 'pages', 'PickPage.tsx'),
];
const P0_FORBIDDEN = [
  [/\bTODAYS_DESK\b/, 'TODAYS_DESK static recommendation literal'],
  [/\bgenerateBriefing\b/, 'generateBriefing (static briefing flow)'],
  [/\bTRACKING_NAMES\b|\bPASSED_ON_TODAY\b|\bCATALYSTS_AHEAD\b/, 'arthosData rec/catalyst literal'],
  [/\bPICK_NARRATIVE\b|\bgetSymbolContext\b|\bgetPosition\b|\bgetPickEvidence\b/, 'static pick narrative/context'],
  [/from ['"][^'"]*data\/arthosData['"]/, 'arthosData import in a live recommendation route'],
];
for (const relRoute of P0_ROUTES) {
  let text;
  try {
    text = readFileSync(join(ROOT, relRoute), 'utf8');
  } catch {
    continue;
  }
  const rel = relRoute.split(sep).join('/');
  text.split('\n').forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')) return;
    for (const [re, reason] of P0_FORBIDDEN) {
      if (re.test(line)) {
        console.error(`✖ ${rel}:${i + 1}  [P0-live] ${reason}`);
        console.error(`    ${line.trim()}`);
        violations++;
      }
    }
  });
}

// ---------------------------------------------------------------------------
// P1 credibility routes — no LOCAL/static performance, win-rate, expectancy,
// or cohort metrics presented as Arth's record. Rewired in the P1 pass.
// ---------------------------------------------------------------------------
const P1_ROUTES = [
  join('src', 'v2', 'pages', 'TrackRecord.tsx'),
  join('src', 'v2', 'pages', 'ArthReportCard.tsx'),
  join('src', 'v2', 'components', 'DecisionDeskHero.tsx'),
];
const P1_FORBIDDEN = [
  [/\bcomputeTrustMetrics\b|\ballCohortStats\b|\bcohortStats\b|\bclassifyCohort\b|\bsufficientSample\b/,
    'local cohort / trust performance metric'],
  [/\bTRACK_RECORD_CLOSED\b|\bEQUITY_TIMELINE\b|\bQUARTERLY_RETROS\b|\bSTARTING_EQUITY\b/,
    'static track-record literal'],
  [/from ['"][^'"]*lib\/arth\/(trustMetrics|cohort|demoSeed|lessonsLearned)['"]/,
    'local performance/demo module import'],
];
for (const relRoute of P1_ROUTES) {
  let text;
  try {
    text = readFileSync(join(ROOT, relRoute), 'utf8');
  } catch {
    continue;
  }
  const rel = relRoute.split(sep).join('/');
  text.split('\n').forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')) return;
    for (const [re, reason] of P1_FORBIDDEN) {
      if (re.test(line)) {
        console.error(`✖ ${rel}:${i + 1}  [P1-credibility] ${reason}`);
        console.error(`    ${line.trim()}`);
        violations++;
      }
    }
  });
}

// ===========================================================================
// GLOBAL FREEZE GUARDS (POST-F1 §E regression hardening).
//
// These scan ALL of apps/web/src (not just src/v2). The trusted financial /
// recommendation surfaces are GREEN; these rules FREEZE that baseline so the
// dormant legacy systems identified in the POST-F1 audit cannot silently
// re-enter a render or calc path.
//
// Each rule carries an ALLOW list enumerating the CURRENT legitimate
// consumers. That enumeration is the mechanism: a NEW file matching the
// pattern fails until it is consciously added here under review. Do NOT add
// entries to grow a surface — allow-list growth is a regression smell.
// ===========================================================================
const SRC_DIR = join(ROOT, 'src');
const SELF = join('scripts', 'lint-canonical-portfolio.mjs');

const norm = (p) => p.split(sep).join('/');

// { re, tag, reason, allow:[relPaths-from-web-root] }
const GLOBAL_RULES = [
  // E1 — aggregate NAV semantics. usePaperSummary is the ALL-PORTFOLIOS
  // aggregate; user-facing portfolio totals must read useCanonicalStockPortfolio.
  // Frozen to the current operator/admin + shell-telemetry consumers.
  {
    re: /\busePaperSummary\b/,
    tag: 'E1-aggregate',
    reason: 'usePaperSummary (ALL-PORTFOLIOS aggregate) — frozen consumer set; user-facing NAV/return/positions/drawdown must use useCanonicalStockPortfolio',
    allow: [
      'src/lib/operator/hooks.ts',                       // definition
      'src/components/shell/TopStrip.tsx',               // non-financial "last run" heartbeat only (NAV is canonical)
      'src/pages/Overview.tsx',                          // system telemetry only (NAV is canonical)
      'src/pages/PortfolioTerminal.tsx',                 // operator/internal dashboard
      'src/components/overview/TradeBlotter.tsx',         // operator/internal
      'src/pages/copilot/CopilotOverview.tsx',           // operator/internal
      'src/components/operator/SystemStatusCard.tsx',    // operator/internal
      'src/components/operator/KeyMetricsRow.tsx',        // operator/internal
      'src/components/operator/SummaryBar.tsx',           // operator/internal
      'src/components/operator/CurrentActionCard.tsx',    // operator/internal
    ],
  },
  // E4 — raw drawdown field. The /paper/equity dd_pct is an all-portfolios
  // aggregate value; never render it. Drawdown comes from useCanonicalDrawdownPct
  // (client-derived, scoped to the canonical portfolio). Zero current accessors.
  {
    re: /\.dd_pct\b/,
    tag: 'E4-raw-drawdown',
    reason: 'raw .dd_pct field access — drawdown must derive from useCanonicalDrawdownPct (canonical-scoped)',
    allow: [],
  },
  // E3 — dead fake-recommendation literals. Confirmed orphaned in the audit;
  // freeze them out of every module so they cannot re-enter a render path.
  // (TODAYS_DESK still has live non-trust consumers and stays governed by the
  // P0 route gate above; it is scheduled for removal in R1.)
  {
    re: /\b(TRACK_RECORD_CLOSED|PASSED_ON_TODAY|PICK_NARRATIVE)\b/,
    tag: 'E3-fake-literal',
    reason: 'dead static recommendation literal — must not be imported/used by any module',
    allow: ['src/v2/data/arthosData.ts'],               // definitions only (deleted in R1)
  },
  // E2 — localStorage financial-state. Freeze the localStorage surface: only
  // the current UI-preference / ephemeral / sandbox stores may touch it. A NEW
  // store (which could hold NAV / equity / positions / portfolio_id-as-truth)
  // fails here. PaperBook + overview_memory carry financial-ish state and are
  // flagged R4 debt — present only to keep the baseline green, not to bless.
  {
    re: /\blocalStorage\s*\.\s*(get|set|remove)Item\b/,
    tag: 'E2-localstorage',
    reason: 'localStorage state surface is frozen — no NEW client-side store (esp. NAV/equity/positions/portfolio_id-as-truth)',
    allow: [
      'src/lib/storage.ts',                              // generic UI-prefs wrapper
      'src/lib/ui/theme.ts',                             // theme pref
      'src/lib/ui/mode.ts',                              // guided/expert mode
      'src/lib/options/guardrailsToggle.tsx',            // UI-only toggle (never drives backend)
      'src/lib/copilot/onboarding.ts',                   // 3 first-run flags
      'src/lib/picks/overview_memory.ts',                // last-Overview snapshot (R4 debt: holds nav for honest delta)
      'src/lib/picks/visited_memory.ts',                 // visited pick ids (bounded)
      'src/components/guidance/GuidancePanel.tsx',       // panel expand/collapse
      'src/components/portfolio/DensityToggle.tsx',      // data-density pref
      'src/v2/state/UserPrefsContext.tsx',               // V2 UI prefs
      'src/v2/state/PaperBook.tsx',                      // V2 sandbox book (R4 debt: holds positions; isolated key)
      'src/v2/pages/Observability.tsx',                  // session sparkline buffer (observed samples)
      'src/v2/chrome/ThemeContext.tsx',                  // V2 theme
      'src/v2/lib/local-store.ts',                       // SSR-safe store helper
      'src/v2/lib/arth/storage.ts',                      // Arth namespaced store (R4 debt)
      'src/v2/lib/arth/useArthStore.ts',                 // Arth store hook (R4 debt)
    ],
  },
  // E5 — demo/mock financial data. No demo-seed import in a production route /
  // component, no DEMO_/MOCK_/FAKE_ data literals. The two URL-param-gated
  // seeds (demoSeed2d/2e) keep their single current consumers; seedReportCardDemo
  // is an orphan and any importer fails here.
  {
    re: /\b(demoSeed|seed[A-Za-z0-9]*Demo)\b/,
    tag: 'E5-demo-seed',
    reason: 'demo/mock seed reachable from a production component — forbidden (URL-gated seeds frozen to current consumers)',
    allow: [
      'src/v2/lib/arth/demoSeed.ts',                     // definition
      'src/v2/lib/arth/demoSeed2d.ts',                   // definition
      'src/v2/lib/arth/demoSeed2e.ts',                   // definition
      'src/v2/components/TodayLessonSlot.tsx',           // ?seed2dLesson= gated
      'src/v2/pages/MentorProfile.tsx',                  // ?seedMentor= gated
    ],
  },
  {
    re: /\b(DEMO|MOCK|FAKE)_[A-Z0-9]/,
    tag: 'E5-mock-literal',
    reason: 'DEMO_/MOCK_/FAKE_ data literal — no mock financial data in production code',
    allow: [],
  },
];

for (const file of walk(SRC_DIR)) {
  const rel = norm(relative(ROOT, file));
  if (rel.endsWith(norm(SELF))) continue;
  const text = readFileSync(file, 'utf8');
  text.split('\n').forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')) return;
    for (const rule of GLOBAL_RULES) {
      if (!rule.re.test(line)) continue;
      if (rule.allow.some((a) => rel.endsWith(norm(a)))) continue;
      console.error(`✖ ${rel}:${i + 1}  [${rule.tag}] ${rule.reason}`);
      console.error(`    ${line.trim()}`);
      violations++;
    }
  });
}

if (violations > 0) {
  console.error(`\nLive-data gate FAILED: ${violations} violation(s).`);
  process.exit(1);
}
console.log('Live-data gate passed: no forbidden portfolio/recommendation/credibility/localStorage/demo reads in apps/web/src.');
