import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const output = path.resolve(here, '../../docs/images');
const title = 'Acme Robotics — sample source audit';
fs.mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 });
page.on('console', (message) => { if (message.type() === 'error') console.error('browser-console:', message.text()); });
page.on('pageerror', (error) => console.error('browser-error:', error.message));

async function capture(name) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.waitForTimeout(150);
  await page.screenshot({ path: path.join(output, name), fullPage: true });
}

try {
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: /Good work starts with good evidence/i })).toBeVisible();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'New analysis' }).click();
  await page.getByRole('button', { name: /Load sample/i }).click();
  await capture('new-analysis.png');

  const existingResponse = await page.request.get('http://127.0.0.1:8000/api/analyses?limit=100');
  const existingPayload = existingResponse.ok() ? await existingResponse.json() : { items: [] };
  const existing = existingPayload.items?.find((item) => item.title === title && item.status === 'completed' && item.total_claims > 0);
  if (existing) {
    await page.goto(`http://127.0.0.1:5173/analysis/${existing.id}`, { waitUntil: 'networkidle' });
  } else {
    await page.getByRole('button', { name: /Start analysis/i }).click();
    await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 20000 });
  }
  await page.waitForFunction(() => document.querySelector('.result-toolbar .status-pill')?.textContent?.toLowerCase().includes('completed'));
  await capture('verification-results.png');

  const claim = page.locator('.claim-list-item').filter({ hasText: 'lunar research station' });
  await claim.click();
  await page.waitForTimeout(250);
  await capture('claim-evidence-detail.png');
  const reviewHistory = page.getByRole('heading', { name: /Human review history/i });
  if (await reviewHistory.count() === 0) {
    await page.getByRole('button', { name: /Record human review/i }).click();
    await page.locator('.detail-review select').selectOption('needs_more_evidence');
    await page.locator('.detail-review textarea').fill('The supplied release discusses laboratory investment, but it does not establish that a lunar research station launched. A separate primary source is needed.');
    await page.getByRole('button', { name: /Save human review/i }).click();
    await expect(reviewHistory).toBeVisible();
  }
  await page.waitForTimeout(350);
  await capture('human-review.png');

  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Overview' }).click();
  await expect(page.getByRole('heading', { name: /Good work starts with good evidence/i })).toBeVisible();
  await page.waitForTimeout(250);
  await capture('dashboard.png');

  await page.getByRole('navigation', { name: 'Preferences' }).getByRole('button', { name: 'Provider settings' }).click();
  await expect(page.getByRole('heading', { name: 'Provider settings' })).toBeVisible();
  await page.waitForTimeout(250);
  await capture('provider-settings.png');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' });
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible();
  await capture('mobile-dashboard.png');
  console.log('Captured genuine application screenshots in', output);
} finally {
  await browser.close();
}
