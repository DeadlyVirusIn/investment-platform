import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', '..', '..', 'docs', 'research', 'Screenshots', 'phase-d-before-2026-05-23');
const HOST = 'http://localhost:5174';
const PAGES = [
  { slug: 'learn', path: '/v2/learn' },
  { slug: 'academy-stocks', path: '/v2/learn/stocks' },
  { slug: 'academy-risk', path: '/v2/learn/risk' },
  { slug: 'academy-options', path: '/v2/learn/options' },
  { slug: 'glossary', path: '/v2/learn/glossary' },
];
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 375, height: 812 },
];
const THEMES = ['light', 'dark'];
const browser = await chromium.launch();
const ctx = await browser.newContext({ deviceScaleFactor: 2 });
for (const p of PAGES) {
  for (const t of THEMES) {
    for (const v of VIEWPORTS) {
      const page = await ctx.newPage();
      await page.setViewportSize({ width: v.width, height: v.height });
      await page.goto(`${HOST}${p.path}?theme=${t}&skipMotion=1&skipOnboarding=1`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(700);
      const file = path.join(OUT, `${p.slug}-${t}-${v.name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`✓ ${path.basename(file)}`);
      await page.close();
    }
  }
}
await browser.close();
