// Capture script for RR (rail-restore) — vision-lock #9 implementation.
// Run on HAIKU model only per global CLAUDE.md.
//
// Prereq: V2 dev server reachable at HOST (default http://localhost:5174).
// If compose-web-1 is the source: ensure the worktree
// feat/v2-rail-restore is checked out in the PRIMARY checkout OR rebuild
// the web container against this worktree before running.

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(
  __dirname, '..', '..', '..',
  'docs', 'research', 'Screenshots', 'rail-restore-2026-05-23',
);
await mkdir(OUT, { recursive: true });

const HOST = process.env.HOST ?? 'http://localhost:5174';

// V2 surfaces that should now render the rail above their content.
const PAGES = [
  { slug: 'today',         path: '/v2/today' },
  { slug: 'learn',         path: '/v2/learn' },
  { slug: 'opportunities', path: '/v2/opportunities' },
  { slug: 'me',            path: '/v2/me' },
];

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile',  width: 375,  height: 812 },
];

const THEMES = ['light', 'dark'];

const browser = await chromium.launch();
const ctx = await browser.newContext({ deviceScaleFactor: 2 });

for (const p of PAGES) {
  for (const t of THEMES) {
    for (const v of VIEWPORTS) {
      const page = await ctx.newPage();
      await page.setViewportSize({ width: v.width, height: v.height });
      const url = `${HOST}${p.path}?theme=${t}&skipMotion=1&skipOnboarding=1`;
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      // Let the sticky rail settle + queries hydrate.
      await page.waitForTimeout(900);
      const file = path.join(OUT, `${p.slug}-${t}-${v.name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`✓ ${path.basename(file)}`);
      await page.close();
    }
  }
}

// Mobile disclosure expanded — capture today/light/mobile with the ▾
// trigger clicked open. Demonstrates decision 2.
{
  const page = await ctx.newPage();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(
    `${HOST}/v2/today?theme=light&skipMotion=1&skipOnboarding=1`,
    { waitUntil: 'networkidle', timeout: 30000 },
  );
  await page.waitForTimeout(700);
  const trigger = await page.$('.v2-rail-disclosure-trigger');
  if (trigger) {
    await trigger.click();
    await page.waitForTimeout(300);
    const file = path.join(OUT, 'today-light-mobile-disclosure-open.png');
    await page.screenshot({ path: file, fullPage: true });
    console.log(`✓ ${path.basename(file)}`);
  } else {
    console.log('⚠ disclosure trigger not found — check selector');
  }
  await page.close();
}

await browser.close();
console.log(`\nOutput: ${OUT}`);
