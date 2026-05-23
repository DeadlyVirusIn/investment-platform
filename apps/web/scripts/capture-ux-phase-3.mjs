// UX Phase 3A — capture the 2 new close-the-loop surfaces +
// the modified lesson page (with new "Try this idea" CTA) +
// the modified Me page (with new learning-loops section).
//
// 4 routes × 2 themes × 2 viewports = 16 PNGs.
// Output: docs/research/Screenshots/ux-phase-3a-2026-05-23/.

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
  'ux-phase-3a-2026-05-23',
);

const HOST = 'http://localhost:5174';

const PAGES = [
  { slug: 'try-reading-a-thesis', path: '/v2/try/reading-a-thesis' },
  { slug: 'reflections',          path: '/v2/reflections' },
  { slug: 'lesson-with-try-cta',  path: '/v2/learn/lesson/reading-a-thesis' },
  { slug: 'me',                   path: '/v2/me' },
];

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile',  width: 375,  height: 812 },
];

const THEMES = ['light', 'dark'];

const QUERY = 'skipMotion=1&skipOnboarding=1';

async function run() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 2 });
  for (const p of PAGES) {
    for (const theme of THEMES) {
      for (const vp of VIEWPORTS) {
        const url = `${HOST}${p.path}?theme=${theme}&${QUERY}`;
        const page = await ctx.newPage();
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(800);
        const file = path.join(
          OUT_DIR,
          `${p.slug}-${theme}-${vp.name}.png`,
        );
        await page.screenshot({ path: file, fullPage: true });
        console.log(`✓ ${path.basename(file)}`);
        await page.close();
      }
    }
  }
  await browser.close();
  console.log('\nDone. Files in', OUT_DIR);
}

run().catch((err) => {
  console.error('Capture failed:', err);
  process.exit(1);
});
