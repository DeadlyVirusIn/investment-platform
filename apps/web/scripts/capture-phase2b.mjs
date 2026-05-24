// Phase 2B capture — Report Card sections, Trust banner, honesty modes.

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(
  __dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'phase2b-2026-05-24',
);
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://127.0.0.1:5177';

const browser = await chromium.launch();
const ctx = await browser.newContext({ deviceScaleFactor: 2 });

async function fresh(viewport = { width: 1440, height: 900 }) {
  const page = await ctx.newPage();
  await page.setViewportSize(viewport);
  await page.goto(`${HOST}/v2/today`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    Object.keys(localStorage).forEach((k) => {
      if (k.startsWith('arthos.v2') || k.startsWith('v2-')) localStorage.removeItem(k);
    });
  });
  return page;
}
async function go(page, p) {
  await page.goto(`${HOST}${p}?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  console.log(`✓ ${name}`);
}

// 1. Today with TrustBanner — fresh (honesty mode: no closed)
{
  const page = await fresh();
  await go(page, '/v2/today');
  await shot(page, '01-today-trustbanner-fresh-desktop');
  await page.close();
}

// 2. Report Card — empty state (honest "too early" voice)
{
  const page = await fresh();
  await go(page, '/v2/arth');
  await shot(page, '02-report-card-empty-honest-desktop');
  await page.close();
}

// 3. Report Card — seeded (full 8 sections + expectancy + cohort)
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?theme=light&skipMotion=1&skipOnboarding=1&seedReportCard=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1200);
  await shot(page, '03-report-card-seeded-full-desktop');
  await page.close();
}

// 4. Report Card — audit trace expanded
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?theme=light&skipMotion=1&skipOnboarding=1&seedReportCard=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);
  // Click "Show me an example audit trace"
  const btn = page.getByRole('button', { name: /Show me an example audit trace/i });
  await btn.click({ timeout: 5000 });
  await page.waitForTimeout(500);
  // Scroll to the bottom to capture the trace
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(300);
  await shot(page, '04-report-card-audit-trace-expanded-desktop');
  await page.close();
}

// 5. Report Card — wins filter
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?theme=light&skipMotion=1&skipOnboarding=1&seedReportCard=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);
  const winsChip = page.getByRole('button', { name: /^wins$/i });
  await winsChip.click({ timeout: 5000 });
  await page.waitForTimeout(400);
  await shot(page, '05-report-card-history-wins-filter-desktop');
  await page.close();
}

// 6. Report Card — seeded mobile
{
  const page = await fresh({ width: 375, height: 812 });
  await page.goto(`${HOST}/v2/arth?theme=light&skipMotion=1&skipOnboarding=1&seedReportCard=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);
  await shot(page, '06-report-card-seeded-mobile');
  await page.close();
}

// 7. Today with TrustBanner — after seeded (banner with real numbers)
{
  const page = await fresh();
  // Seed via Report Card route first so storage carries the data
  await page.goto(`${HOST}/v2/arth?seedReportCard=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await go(page, '/v2/today');
  await shot(page, '07-today-trustbanner-seeded-desktop');
  await page.close();
}

// 8. Report Card — dark theme
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?theme=dark&skipMotion=1&skipOnboarding=1&seedReportCard=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);
  await shot(page, '08-report-card-seeded-dark-desktop');
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
