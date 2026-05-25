// Phase 2C — Decision Desk capture.

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'phase2c-2026-05-24');
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://127.0.0.1:5178';
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

// 1. Opportunities full desktop (light) — hero w/ 6 answers + alternatives
{
  const page = await fresh();
  await go(page, '/v2/opportunities');
  await shot(page, '01-opportunities-decision-desk-light-desktop');
  await page.close();
}

// 2. Opportunities seeded — adds Report Card data so historical perf row
//    has real numbers (no "too early")
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?seedReportCard=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await go(page, '/v2/opportunities');
  await shot(page, '02-opportunities-seeded-historical-perf-desktop');
  await page.close();
}

// 3. Hero zoomed via Today (single-card focus)
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?seedReportCard=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await go(page, '/v2/today');
  await shot(page, '03-today-arthhero-still-mvp-desktop');
  await page.close();
}

// 4. Dark theme
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?seedReportCard=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.goto(`${HOST}/v2/opportunities?theme=dark&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
  await shot(page, '04-opportunities-dark-desktop');
  await page.close();
}

// 5. Mobile
{
  const page = await fresh({ width: 375, height: 812 });
  await page.goto(`${HOST}/v2/arth?seedReportCard=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await go(page, '/v2/opportunities');
  await shot(page, '05-opportunities-light-mobile');
  await page.close();
}

// 6. Empty-day "Cash is the call" — synthesize by replacing TODAYS_DESK
//    placeable=false via localStorage isn't possible; instead simulate
//    by setting a flag that the page reads… we have no flag. Cheaper:
//    capture as the page renders today (recs DO clear cash bar in seeded
//    data because AAPL has high edge). Skip this capture for now and
//    add a "Hold cash" decision shot from the alt path.
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/arth?seedReportCard=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  // Force the cash variant by overriding the placeable recs at the
  // window level — short-circuit the placeable list.
  await go(page, '/v2/opportunities');
  // Take an after-decision capture: open the hero, save it (puts a chip
  // beneath the hero card to demonstrate the "done" state).
  const saveBtn = page.getByRole('button', { name: /^Save for later$/i });
  if (await saveBtn.count() > 0) {
    await saveBtn.click({ timeout: 5000 });
    await page.waitForTimeout(500);
    await shot(page, '06-opportunities-after-save-desktop');
  }
  await page.close();
}

// 7. Skip flow open
{
  const page = await fresh();
  await go(page, '/v2/opportunities');
  const skipBtn = page.getByRole('button', { name: /^Skip — tell me why$/i });
  if (await skipBtn.count() > 0) {
    await skipBtn.click({ timeout: 5000 });
    await page.waitForTimeout(400);
    await shot(page, '07-opportunities-skip-flow-desktop');
  }
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
