import { expect, test } from '@playwright/test';

test('user completes a local analysis and records a human review', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Good work starts with good evidence/i })).toBeVisible();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'New analysis' }).click();
  await page.getByRole('button', { name: /Load sample/i }).click();
  await expect(page.getByLabel('AI-generated text')).toContainText('Acme Robotics');
  await page.getByRole('button', { name: /Start analysis/i }).click();
  await expect(page.getByText('VERIFICATION REPORT', { exact: true })).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole('heading', { name: 'Acme Robotics — sample source audit' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Retrieved evidence/ })).toBeVisible();
  await expect(page.locator('.claim-list-item').filter({ hasText: 'lunar research station' })).toBeVisible();
  await page.locator('.claim-list-item').filter({ hasText: 'lunar research station' }).click();
  await page.getByRole('button', { name: /Record human review/i }).click();
  await page.locator('select').last().selectOption('needs_more_evidence');
  await page.locator('textarea').last().fill('The attached release does not mention a lunar station.');
  await page.getByRole('button', { name: /Save human review/i }).click();
  await expect(page.getByText(/Human review history/i)).toBeVisible();
  await expect(page.getByText(/needs more evidence/i).first()).toBeVisible();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'History' }).click();
  await expect(page.getByRole('heading', { name: 'Analysis history' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Acme Robotics — sample source audit/i }).first()).toBeVisible();
  expect(consoleErrors.filter((text) => !text.includes('favicon'))).toEqual([]);
});

test('provider settings are connected to the local configuration endpoint', async ({ page }) => {
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: 'Provider settings' })).toBeVisible();
  await page.getByRole('button', { name: /Test connection/i }).click();
  await expect(page.getByText(/Local deterministic analysis is ready/i)).toBeVisible();
  await expect(page.getByText(/Local, by design/i)).toBeVisible();
});

test('mobile navigation and analysis form fit a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible();
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'New analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Verify an AI-generated answer' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Start analysis/i })).toBeVisible();
});
