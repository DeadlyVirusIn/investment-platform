// Comprehensive Arth MVP capture — every state the user asked for.
import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(
  __dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'arth-mvp-v2-2026-05-24',
);
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://127.0.0.1:5176';

const browser = await chromium.launch();
const ctx = await browser.newContext({ deviceScaleFactor: 2 });

async function freshPage(viewport = { width: 1440, height: 900 }) {
  const page = await ctx.newPage();
  await page.setViewportSize(viewport);
  // Visit once to attach storage
  await page.goto(`${HOST}/v2/today`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    Object.keys(localStorage).forEach((k) => {
      if (k.startsWith('arthos.v2')) localStorage.removeItem(k);
    });
  });
  return page;
}

async function go(page, path) {
  await page.goto(`${HOST}${path}?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
}

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`✓ ${name}`);
}

// ── DESKTOP ────────────────────────────────────────────────

// 1. Today (fresh Day 1)
{
  const page = await freshPage();
  await go(page, '/v2/today');
  await shot(page, '01-today-fresh-day1-desktop');
  await page.close();
}

// 2. Today after Follow + reflection submitted (DONE state with Arth's
//    responsive line and reflection acknowledged)
{
  const page = await freshPage();
  await go(page, '/v2/today');
  await page.getByRole('button', { name: /Paper trade this/i }).click();
  await page.waitForTimeout(400);
  await page.locator('textarea').fill('I expect AAPL to grind higher into the quiet pre-earnings tape — option premium should erode in my favor.');
  await page.getByRole('button', { name: /^Save$/ }).click();
  await page.waitForTimeout(500);
  await shot(page, '02-today-after-follow-desktop');
  await page.close();
}

// 3. Today after Skip-with-reason (DONE state with skip acknowledgement)
{
  const page = await freshPage();
  await go(page, '/v2/today');
  await page.getByRole('button', { name: /Skip — tell me why/i }).click();
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: /Earnings risk/ }).click();
  await page.waitForTimeout(500);
  await shot(page, '03-today-after-skip-desktop');
  await page.close();
}

// 4. Today after Paper Trade — same as after-follow but capture the
//    intermediate stage where reflection prompt is *visible but not yet
//    submitted*.
{
  const page = await freshPage();
  await go(page, '/v2/today');
  await page.getByRole('button', { name: /Paper trade this/i }).click();
  await page.waitForTimeout(500);
  await shot(page, '04-today-after-papertrade-desktop');
  await page.close();
}

// 5. Reflection capture state (textarea focused with sample text)
{
  const page = await freshPage();
  await go(page, '/v2/today');
  await page.getByRole('button', { name: /Paper trade this/i }).click();
  await page.waitForTimeout(400);
  await page.locator('textarea').fill('I expect the implied vol to keep falling — that\'s the edge.');
  await page.waitForTimeout(300);
  await shot(page, '05-reflection-capture-desktop');
  await page.close();
}

// 6. Journal populated — after a Follow + Reflection + Skip
{
  const page = await freshPage();
  await go(page, '/v2/today');
  // Action 1: Follow + reflect
  await page.getByRole('button', { name: /Paper trade this/i }).click();
  await page.waitForTimeout(300);
  await page.locator('textarea').fill('I expect implied vol to keep falling.');
  await page.getByRole('button', { name: /^Save$/ }).click();
  await page.waitForTimeout(400);
  // Action 2: visit Today again — same-day dedupe protects the existing rec
  // so to add a second decision row, navigate to journal and observe.
  await go(page, '/v2/journal');
  await shot(page, '06-journal-populated-desktop');
  await page.close();
}

// 7. Opportunities
{
  const page = await freshPage();
  await go(page, '/v2/opportunities');
  await shot(page, '07-opportunities-desktop');
  await page.close();
}

// 8. Learn
{
  const page = await freshPage();
  await go(page, '/v2/learn');
  await shot(page, '08-learn-desktop');
  await page.close();
}

// 9. Me
{
  const page = await freshPage();
  await go(page, '/v2/me');
  await shot(page, '09-me-desktop');
  await page.close();
}

// ── MOBILE ────────────────────────────────────────────────

// 10. Today mobile (fresh Day 1)
{
  const page = await freshPage({ width: 375, height: 812 });
  await go(page, '/v2/today');
  await shot(page, '10-today-mobile');
  await page.close();
}

// 11. Reflection capture mobile
{
  const page = await freshPage({ width: 375, height: 812 });
  await go(page, '/v2/today');
  await page.getByRole('button', { name: /Paper trade this/i }).click();
  await page.waitForTimeout(400);
  await page.locator('textarea').fill('Implied vol should fall.');
  await page.waitForTimeout(300);
  await shot(page, '11-reflection-capture-mobile');
  await page.close();
}

// 12. Journal mobile (populated)
{
  const page = await freshPage({ width: 375, height: 812 });
  await go(page, '/v2/today');
  await page.getByRole('button', { name: /Paper trade this/i }).click();
  await page.waitForTimeout(300);
  await page.locator('textarea').fill('I expect vol to fall.');
  await page.getByRole('button', { name: /^Save$/ }).click();
  await page.waitForTimeout(400);
  await go(page, '/v2/journal');
  await shot(page, '12-journal-mobile');
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
