import { test, expect } from '@playwright/test';

function getBaseUrl(): string {
  // Prefer explicit env var (GitHub Actions / local).
  const env = process.env.E2E_BASE_URL?.trim();
  if (env) return env.replace(/\/+$/, '');

  // Fallback: live Wissen root.
  return 'https://www.vertaefelungen.de/wissen';
}

test.describe('Live navigation (Wissen)', () => {
  test('DE live navigation', async ({ page }) => {
    const base = getBaseUrl();
    await page.goto(`${base}/de/`, { waitUntil: 'domcontentloaded' });

    // Log URL to make baseURL/redirect issues obvious in CI logs.
    // eslint-disable-next-line no-console
    console.log('Visited URL (DE):', page.url());

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 20000 });

    // Header menu: scope to header nav to avoid strict mode violations (same link text elsewhere).
    const headerNav = page.locator('header.site-header nav#main-nav');
    const scopedHeaderNav = (await headerNav.count()) ? headerNav : page.locator('header.site-header nav');
    await expect(scopedHeaderNav).toBeVisible({ timeout: 20000 });
    const productsLink = scopedHeaderNav.getByRole('link', { name: 'Produkte', exact: true });
    if (await productsLink.count()) {
      await expect(productsLink).toBeVisible({ timeout: 20000 });
      await productsLink.click();
      await expect(page).toHaveURL(/\/wissen\/de\/produkte\/?$/i, { timeout: 20000 });
    } else {
      // Fallback: ensure the "Produkte" card exists on the start page.
      await expect(page.getByRole('heading', { name: 'Produkte', exact: true })).toBeVisible({ timeout: 20000 });
    }
  });

  test('EN live navigation', async ({ page }) => {
    const base = getBaseUrl();
    await page.goto(`${base}/en/`, { waitUntil: 'domcontentloaded' });

    // eslint-disable-next-line no-console
    console.log('Visited URL (EN):', page.url());

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 20000 });

    const headerNav = page.locator('header.site-header nav#main-nav');
    const scopedHeaderNav = (await headerNav.count()) ? headerNav : page.locator('header.site-header nav');
    await expect(scopedHeaderNav).toBeVisible({ timeout: 20000 });
    const productsLink = scopedHeaderNav.getByRole('link', { name: 'Products', exact: true });
    if (await productsLink.count()) {
      await expect(productsLink).toBeVisible({ timeout: 20000 });
      await productsLink.click();
      await expect(page).toHaveURL(/\/wissen\/en\/products\/?$/i, { timeout: 20000 });
    } else {
      await expect(page.getByRole('heading', { name: 'Products', exact: true })).toBeVisible({ timeout: 20000 });
    }
  });
});
