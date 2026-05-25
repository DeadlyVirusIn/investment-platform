// Phase 2E — Mentor Profile capture.

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'phase2e-2026-05-24');
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://127.0.0.1:5180';
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
async function go(page, p, extra = '') {
  await page.goto(`${HOST}${p}?theme=light&skipMotion=1&skipOnboarding=1${extra}`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  console.log(`✓ ${name}`);
}

// 1. /v2/me fresh — everything in "Too early to tell" honesty mode
{
  const page = await fresh();
  await go(page, '/v2/me');
  await shot(page, '01-mentor-fresh-honesty-desktop');
  await page.close();
}

// 2. /v2/me seeded — full populated relationship document
{
  const page = await fresh();
  await go(page, '/v2/me', '&seedMentor=1');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, '02-mentor-seeded-full-desktop');
  await page.close();
}

// 3. Pattern dispute interaction
{
  const page = await fresh();
  await go(page, '/v2/me', '&seedMentor=1');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const disputeBtn = page.getByRole('button', { name: /No, I had reasons/i }).first();
  if ((await disputeBtn.count()) > 0) {
    await disputeBtn.click({ timeout: 5000 });
    await page.waitForTimeout(600);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    await shot(page, '03-mentor-pattern-disputed-desktop');
  } else {
    console.log('  (no dispute button found — capturing without)');
    await shot(page, '03-mentor-pattern-disputed-desktop');
  }
  await page.close();
}

// 4. Pattern confirmed interaction
{
  const page = await fresh();
  await go(page, '/v2/me', '&seedMentor=1');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const confirmBtn = page.getByRole('button', { name: /Yes, that's me/i }).first();
  if ((await confirmBtn.count()) > 0) {
    await confirmBtn.click({ timeout: 5000 });
    await page.waitForTimeout(600);
    await shot(page, '04-mentor-pattern-confirmed-desktop');
  }
  await page.close();
}

// 5. Mobile seeded
{
  const page = await fresh({ width: 375, height: 812 });
  await go(page, '/v2/me', '&seedMentor=1');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, '05-mentor-seeded-mobile');
  await page.close();
}

// 6. Dark
{
  const page = await fresh();
  await page.goto(`${HOST}/v2/me?theme=dark&skipMotion=1&skipOnboarding=1&seedMentor=1`,
    { waitUntil: 'networkidle', timeout: 30000 });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, '06-mentor-seeded-dark-desktop');
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
