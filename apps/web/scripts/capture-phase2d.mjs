// Phase 2D — contextual learning capture.

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'phase2d-2026-05-24');
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://127.0.0.1:5179';
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
async function go(page, p, extra='') {
  await page.goto(`${HOST}${p}?theme=light&skipMotion=1&skipOnboarding=1${extra}`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  console.log(`✓ ${name}`);
}

// 1. Today fresh — no lesson surfaced (honesty: no trigger)
{
  const page = await fresh();
  await go(page, '/v2/today');
  await shot(page, '01-today-no-lesson-honesty-desktop');
  await page.close();
}

// 2. Today with seeded earnings-risk skip pattern — TodayLessonSlot fires
{
  const page = await fresh();
  await go(page, '/v2/today', '&seed2dLesson=1');
  await page.waitForTimeout(800);
  // reload so the pattern scan + storage subscriber flow renders
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await shot(page, '02-today-pattern-lesson-fired-desktop');
  await page.close();
}

// 3. Same as #2 — click "Give me the full 2-min lesson"
{
  const page = await fresh();
  await go(page, '/v2/today', '&seed2dLesson=1');
  await page.waitForTimeout(800);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const expand = page.getByRole('button', { name: /Give me the full 2-min lesson/i });
  await expand.click({ timeout: 5000 });
  await page.waitForTimeout(400);
  await shot(page, '03-today-lesson-expanded-desktop');
  await page.close();
}

// 4. Skip-with-reason on Opportunities triggers lesson inline
{
  const page = await fresh();
  await go(page, '/v2/opportunities');
  const skipBtn = page.getByRole('button', { name: /^Skip — tell me why$/i });
  await skipBtn.click({ timeout: 5000 });
  await page.waitForTimeout(400);
  const reasonBtn = page.getByRole('button', { name: /^Earnings risk$/i });
  await reasonBtn.click({ timeout: 5000 });
  await page.waitForTimeout(700);
  await shot(page, '04-opportunities-skip-fires-lesson-desktop');
  await page.close();
}

// 5. Quick-check correct answer → learned
{
  const page = await fresh();
  await go(page, '/v2/opportunities');
  await page.getByRole('button', { name: /^Skip — tell me why$/i }).click();
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: /^Earnings risk$/i }).click();
  await page.waitForTimeout(700);
  // Open quick check
  await page.getByRole('button', { name: /I've got it — quick check/i }).click();
  await page.waitForTimeout(400);
  // Pick the correct answer ("Your calls may still lose value because IV crushed back to normal.")
  const correctOpt = page.getByRole('button', {
    name: /Your calls may still lose value because IV crushed back to normal/i,
  });
  await correctOpt.click({ timeout: 5000 });
  await page.waitForTimeout(200);
  await page.getByRole('button', { name: /^Submit$/i }).click();
  await page.waitForTimeout(500);
  await shot(page, '05-quick-check-passed-learned-desktop');
  await page.close();
}

// 6. Mobile — Today with pattern lesson
{
  const page = await fresh({ width: 375, height: 812 });
  await go(page, '/v2/today', '&seed2dLesson=1');
  await page.waitForTimeout(800);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await shot(page, '06-today-lesson-mobile');
  await page.close();
}

// 7. Dark theme
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/today?theme=dark&skipMotion=1&skipOnboarding=1&seed2dLesson=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await shot(page, '07-today-lesson-dark-desktop');
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
