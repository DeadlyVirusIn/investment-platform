// Arth MVP capture — Today + Decision + Reflection + Journal end-to-end.

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(
  __dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'arth-mvp-2026-05-24',
);
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://127.0.0.1:5176';

const browser = await chromium.launch();
const ctx = await browser.newContext({
  deviceScaleFactor: 2,
  viewport: { width: 1440, height: 900 },
});

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`✓ ${name}`);
}

// 1. Today — initial (Day 1 — opening, hero, decision row idle)
{
  const page = await ctx.newPage();
  await page.goto(`${HOST}/v2/today?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
  await shot(page, '01-today-day1-light-desktop');
  await page.close();
}

// 2. Today dark
{
  const page = await ctx.newPage();
  await page.goto(`${HOST}/v2/today?theme=dark&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
  await shot(page, '02-today-day1-dark-desktop');
  await page.close();
}

// 3. Today mobile
{
  const page = await ctx.newPage();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${HOST}/v2/today?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
  await shot(page, '03-today-day1-light-mobile');
  await page.close();
}

// 4. Today — skip-with-reason chips open
{
  const page = await ctx.newPage();
  await page.goto(`${HOST}/v2/today?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(800);
  // Click the skip-tell-me-why button
  const skipBtn = page.getByRole('button', { name: /Skip — tell me why/i });
  await skipBtn.click({ timeout: 5000 });
  await page.waitForTimeout(400);
  await shot(page, '04-decide-skip-reasons-light-desktop');
  await page.close();
}

// 5. Today — after follow → reflection capture stage
{
  const page = await ctx.newPage();
  await page.goto(`${HOST}/v2/today?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(800);
  // Clear arth namespace so we get the idle state, not a prior decision
  await page.evaluate(() => {
    Object.keys(localStorage).forEach((k) => {
      if (k.startsWith('arthos.v2')) localStorage.removeItem(k);
    });
  });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const followBtn = page.getByRole('button', { name: /Paper trade this/i });
  await followBtn.click({ timeout: 5000 });
  await page.waitForTimeout(500);
  await shot(page, '05-practice-reflection-capture-light-desktop');
  await page.close();
}

// 6. Today — done state (after reflection submitted)
{
  const page = await ctx.newPage();
  await page.goto(`${HOST}/v2/today?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(800);
  // Reuse existing local storage (carries the paper trade just opened)
  await shot(page, '06-today-after-decide-light-desktop');
  await page.close();
}

// 7. Journal — populated
{
  const page = await ctx.newPage();
  await page.goto(`${HOST}/v2/journal?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(800);
  await shot(page, '07-journal-populated-light-desktop');
  await page.close();
}

// 8. Journal mobile
{
  const page = await ctx.newPage();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${HOST}/v2/journal?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(800);
  await shot(page, '08-journal-light-mobile');
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
