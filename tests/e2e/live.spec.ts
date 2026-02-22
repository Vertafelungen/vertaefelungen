/**
 * File: tests/e2e/live.spec.ts
 * Version: 2026-02-22 18:45 Europe/Berlin
 * Purpose:
 *   Live smoke tests against production Wissen (DE/EN).
 * Notes:
 *   CI can sporadically time out on navigation due to transient network/CDN/TTFB variance.
 *   We make navigation more resilient without weakening semantic assertions.
 * Change:
 *   - Drawer legal links now point to canonical Shop pages (SSOT), so E2E asserts those hrefs.
 */

import { test, expect, type Page, type Locator } from '@playwright/test';

function getBaseUrl(): string {
  const env = process.env.E2E_BASE_URL?.trim();
  if (env) return env.replace(/\/+$/, '');
  return 'https://www.vertaefelungen.de/wissen';
}

async function gotoWithRetry(page: Page, url: string): Promise<void> {
  const navOpts = { waitUntil: 'load' as const, timeout: 90_000 };

  try {
    await page.goto(url, navOpts);
    return;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('Navigation failed, retrying once:', url, err);

    await page.waitForTimeout(1500);
    await page.goto(url, navOpts);
  }
}

async function assertPrimaryNavLinks(primaryNav: Locator, lang: 'de' | 'en'): Promise<void> {
  const hrefs = await primaryNav.locator('a').evaluateAll((links) =>
    links.map((link) => link.getAttribute('href'))
  );

  expect(hrefs).toHaveLength(4);

  for (const href of hrefs) {
    expect(href).not.toBeNull();
    expect(href).not.toBe('');
    expect(href).toContain(`/wissen/${lang}/`);
  }
}

async function assertDrawerNavigation(page: Page, lang: 'de' | 'en'): Promise<void> {
  const hamburgerButton = page.getByTestId('hamburger-button');
  await expect(hamburgerButton).toBeVisible({ timeout: 20_000 });

  const ariaLabel = await hamburgerButton.getAttribute('aria-label');
  expect(ariaLabel).not.toBeNull();
  expect(ariaLabel?.trim()).not.toBe('');

  await hamburgerButton.click();

  const drawer = page.getByTestId('nav-drawer');
  await expect(drawer).toBeVisible({ timeout: 20_000 });
  await expect(hamburgerButton).toHaveAttribute('aria-expanded', 'true');

  const mainSection = page.getByTestId('drawer-main-links');
  await expect(mainSection.locator('a')).toHaveCount(4);
  await expect(mainSection.locator(`a[href*=\"/wissen/${lang}/shop/\"]`)).toHaveCount(1);
  await expect(mainSection.locator(`a[href*=\"/wissen/${lang}/faq/\"]`)).toHaveCount(1);

  const productsPath = lang === 'de' ? 'produkte' : 'products';
  await expect(mainSection.locator(`a[href*=\"/wissen/${lang}/${productsPath}/\"]`)).toHaveCount(1);
  await expect(mainSection.locator(`a[href*=\"/wissen/${lang}/lookbook/\"]`)).toHaveCount(1);

  const footerSection = page.getByTestId('drawer-footer-links');

  if (lang === 'de') {
    await expect(footerSection.locator('a[href*="/de/content/2-impressum"]')).toHaveCount(1);
    await expect(footerSection.locator('a[href*="/de/content/7-datenschutzerklaerung"]')).toHaveCount(1);
  } else {
    await expect(footerSection.locator('a[href*="/en/content/2-Imprint"]')).toHaveCount(1);
    await expect(footerSection.locator('a[href*="/en/content/7-datenschutzerklaerung"]')).toHaveCount(1);
  }

  await page.keyboard.press('Escape');
  await expect(drawer).not.toBeVisible({ timeout: 20_000 });
  await expect(hamburgerButton).toHaveAttribute('aria-expanded', 'false');
}

test.describe('Live navigation (Wissen)', () => {
  test('DE live navigation', async ({ page }) => {
    test.setTimeout(120_000);
    page.setDefaultNavigationTimeout(90_000);
    page.setDefaultTimeout(30_000);

    const base = getBaseUrl();
    await gotoWithRetry(page, `${base}/de/`);

    // eslint-disable-next-line no-console
    console.log('Visited URL (DE):', page.url());

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 20_000 });

    const primaryNav = page.getByTestId('primary-nav');
    await expect(primaryNav).toBeVisible({ timeout: 20_000 });
    await expect(primaryNav.locator('a')).toHaveCount(4);
    await assertPrimaryNavLinks(primaryNav, 'de');

    await expect(primaryNav.locator('a[href*="ueber-uns"], a[href*="about-us"]')).toHaveCount(0);

    await assertDrawerNavigation(page, 'de');
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

    const primaryNav = page.getByTestId('primary-nav');
    await expect(primaryNav).toBeVisible({ timeout: 20_000 });
    await expect(primaryNav.locator('a')).toHaveCount(4);
    await assertPrimaryNavLinks(primaryNav, 'en');

    await expect(primaryNav.locator('a[href*="ueber-uns"], a[href*="about-us"]')).toHaveCount(0);

    await assertDrawerNavigation(page, 'en');
  });
});
