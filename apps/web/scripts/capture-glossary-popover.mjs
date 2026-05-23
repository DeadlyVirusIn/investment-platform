// Glossary popover open-state capture.
//
// Walks /v2/learn/glossary, clicks the first GlossaryPopover trigger
// (the "thesis" term in alphabetical order — but uses CSS selector
// so any first underlined term works), waits for the radix popover
// content to render, and screenshots the page in 4 variants.
//
// Output: docs/research/Screenshots/lovable-port-2026-05-23/
//   glossary-popover-open-{light,dark}-{desktop,mobile}.png

import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const OUT_DIR = path.join(
  REPO_ROOT,
  'docs',
  'research',
  'Screenshots',
  'lovable-port-2026-05-23',
);

const HOST = 'http://localhost:5174';
const URL_BASE = `${HOST}/v2/learn/glossary`;

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 375, height: 812 },
];

const THEMES = ['light', 'dark'];

async function run() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 2 });

  for (const theme of THEMES) {
    for (const vp of VIEWPORTS) {
      const url = `${URL_BASE}?theme=${theme}&skipMotion=1&skipOnboarding=1`;
      const page = await ctx.newPage();
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(500);

      // GlossaryPopover trigger renders as <button aria-label="Definition of …">
      // (Phase 2 popover). Pick the first one in DOM order — alphabetically
      // sorted in GlossaryIndex, so it'll be "call option".
      const trigger = page.locator('button[aria-label^="Definition of"]').first();
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();

      // Wait for radix popover content to render. Radix sets data-state="open"
      // on the Content element when the popover is open.
      await page
        .locator('[data-radix-popper-content-wrapper]')
        .first()
        .waitFor({ state: 'visible', timeout: 5000 });

      // Let the layout settle.
      await page.waitForTimeout(400);

      const file = path.join(
        OUT_DIR,
        `glossary-popover-open-${theme}-${vp.name}.png`,
      );
      // viewport-sized (not fullPage) — popover is positioned relative to
      // trigger which lives in the visible viewport after scrollIntoView.
      await page.screenshot({ path: file, fullPage: false });
      console.log(`✓ ${path.basename(file)}`);
      await page.close();
    }
  }

  await browser.close();
  console.log('\nDone. Files in', OUT_DIR);
}

run().catch((err) => {
  console.error('Capture failed:', err);
  process.exit(1);
});
