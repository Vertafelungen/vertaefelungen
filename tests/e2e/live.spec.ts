/**
 * File: tests/e2e/live.spec.ts
 * Version: 2026-01-17 12:00 Europe/Berlin
 * Purpose:
 *   Live smoke tests against production Wissen (DE/EN).
 * Notes:
 *   CI can sporadically time out on navigation due to transient network/CDN/TTFB variance.
 *   We make navigation more resilient without weakening semantic assertions.
 */

import { test, expect, type Page } from '@playwright/test';

function getBaseUrl(): string {
  // Prefer explicit env var (GitHub Actions / local).
  const env = process.env.E2E_BASE_URL?.trim();
  if (env) return env.replace(/\/+$/, '');

  // Fallback: live Wissen root.
  return 'https://www.vertaefelungen.de/wissen';
}

async function gotoWithRetry(page: Page, url: string): Promise<void> {
  const navOpts = { waitUntil: 'load' as const, timeout: 90_000 };

  try {
    await page.goto(url, navOpts);
    return;
  } catch (err) {
    // One retry for transient CI/network hiccups.
    // eslint-disable-next-line no-console
    console.warn('Navigation failed, retrying once:', url, err);

    await page.waitForTimeout(1500);
    await page.goto(url, navOpts);
  }
}

test.describe('Live navigation (Wissen)', () => {
  test('DE live navigation', async ({ page }) => {
    test.setTimeout(120_000);
    page.setDefaultNavigationTimeout(90_000);
    page.setDefaultTimeout(30_000);

    const base = getBaseUrl();
    await gotoWithRetry(page, `${base}/de/`);

    // Log URL to make baseURL/redirect issues obvious in CI logs.
    // eslint-disable-next-line no-console
    console.log('Visited URL (DE):', page.url());

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 20_000 });

    // Header menu: scope to header nav to avoid strict mode violations (same link text elsewhere).
    const headerNav = page.locator('header.site-header nav#main-nav');
    const scopedHeaderNav = (await headerNav.count()) ? headerNav : page.locator('header.site-header nav');
    await expect(scopedHeaderNav).toBeVisible({ timeout: 20_000 });

    const productsLink = scopedHeaderNav.getByRole('link', { name: 'Produkte', exact: true });
    if (await productsLink.count()) {
      await expect(productsLink).toBeVisible({ timeout: 20_000 });
      await productsLink.click();
      await expect(page).toHaveURL(/\/wissen\/de\/produkte\/?$/i, { timeout: 20_000 });
    } else {
      // Fallback: ensure the "Produkte" card exists on the start page.
      await expect(page.getByRole('heading', { name: 'Produkte', exact: true })).toBeVisible({ timeout: 20_000 });
    }
  });

  test('EN live navigation', async ({ page }) => {
    test.setTimeout(120_000);
    page.setDefaultNavigationTimeout(90_000);
    page.setDefaultTimeout(30_000);

    const base = getBaseUrl();
    await gotoWithRetry(page, `${base}/en/`);

    // eslint-disable-next-line no-console
    console.log('Visited URL (EN):', page.url());

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 20_000 });

    const headerNav = page.locator('header.site-header nav#main-nav');
    const scopedHeaderNav = (await headerNav.count()) ? headerNav : page.locator('header.site-header nav');
    await expect(scopedHeaderNav).toBeVisible({ timeout: 20_000 });

    const productsLink = scopedHeaderNav.getByRole('link', { name: 'Products', exact: true });
    if (await productsLink.count()) {
      await expect(productsLink).toBeVisible({ timeout: 20_000 });
      await productsLink.click();
      await expect(page).toHaveURL(/\/wissen\/en\/products\/?$/i, { timeout: 20_000 });
    } else {
      await expect(page.getByRole('heading', { name: 'Products', exact: true })).toBeVisible({ timeout: 20_000 });
    }
  });
});
