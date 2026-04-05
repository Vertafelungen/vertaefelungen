/**
 * File: tests/e2e/live.spec.ts
 * Version: 2026-02-22 19:20 Europe/Berlin
 *
 * Purpose:
 *   Live smoke tests against production Wissen (DE/EN).
 *
 * Change:
 *   - Align navigation assertions with /info/ (URLs migrated from /faq/ -> /info/).
 *   - Keep legal links assertions for drawer footer (Shop SSOT targets).
 *   - Add small retry on navigation to reduce transient CI flakiness.
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
    // One retry for transient CI/network hiccups.
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

  // Required links (URL-migrated: /info/)
  await expect(primaryNav.locator(`a[href*="/wissen/${lang}/shop/"]`)).toHaveCount(1);
  await expect(primaryNav.locator(`a[href*="/wissen/${lang}/info/"]`)).toHaveCount(1);
  await expect(primaryNav.locator(`a[href*="/wissen/${lang}/faq/"]`)).toHaveCount(0);

  const productsPath = lang === 'de' ? 'produkte' : 'products';
  await expect(primaryNav.locator(`a[href*="/wissen/${lang}/${productsPath}/"]`)).toHaveCount(1);
  await expect(primaryNav.locator(`a[href*="/wissen/${lang}/lookbook/"]`)).toHaveCount(1);
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
  await expect(mainSection.locator(`a[href*="/wissen/${lang}/shop/"]`)).toHaveCount(1);

  // URL migrated: /faq/ -> /info/
  await expect(mainSection.locator(`a[href*="/wissen/${lang}/info/"]`)).toHaveCount(1);
  await expect(mainSection.locator(`a[href*="/wissen/${lang}/faq/"]`)).toHaveCount(0);

  const productsPath = lang === 'de' ? 'produkte' : 'products';
  await expect(mainSection.locator(`a[href*="/wissen/${lang}/${productsPath}/"]`)).toHaveCount(1);
  await expect(mainSection.locator(`a[href*="/wissen/${lang}/lookbook/"]`)).toHaveCount(1);

  const productsToggle = drawer.getByTestId('drawer-products-toggle').first();
  await expect(productsToggle).toBeVisible();
  await expect(productsToggle).toHaveAttribute('aria-expanded', 'false');

  const controlsId = await productsToggle.getAttribute('aria-controls');
  expect(controlsId).not.toBeNull();
  const productsTree = page.getByTestId('drawer-products-tree');
  await expect(productsTree).toHaveAttribute('id', controlsId ?? '');
  await expect(productsTree).toBeHidden();

  await productsToggle.click();
  await expect(productsToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(productsTree).toBeVisible();

  const drawerProductsPanel = page.getByTestId('drawer-products-panel');
  await expect(drawerProductsPanel).toBeVisible();
  await expect(mainSection.getByTestId('drawer-products-panel')).toHaveCount(0);
  expect(await drawerProductsPanel.locator('a').count()).toBeGreaterThan(0);

  const footerSection = page.getByTestId('drawer-footer-links');

  // Drawer footer legal links now point to canonical Shop pages (SSOT).
  if (lang === 'de') {
    await expect(footerSection.locator('a[href*="/de/content/2-impressum"]')).toHaveCount(1);
    await expect(
      footerSection.locator('a[href*="/de/content/3-allgemeine-geschaeftsbedingungen"]')
    ).toHaveCount(1);
    await expect(footerSection.locator('a[href*="/de/content/7-datenschutzerklaerung"]')).toHaveCount(1);
    await expect(footerSection.locator('a[href*="/de/content/8-widerrufsbelehrung"]')).toHaveCount(1);
  } else {
    await expect(footerSection.locator('a[href*="/en/content/2-Imprint"]')).toHaveCount(1);
    await expect(
      footerSection.locator('a[href*="/en/content/3-allgemeine-geschaeftsbedingungen"]')
    ).toHaveCount(1);
    await expect(footerSection.locator('a[href*="/en/content/7-datenschutzerklaerung"]')).toHaveCount(1);
    await expect(footerSection.locator('a[href*="/en/content/8-widerrufsbelehrung"]')).toHaveCount(1);
  }

  await page.keyboard.press('Escape');
  await expect(drawer).not.toBeVisible({ timeout: 20_000 });
  await expect(hamburgerButton).toHaveAttribute('aria-expanded', 'false');
}

async function assertDesktopMegaMenu(page: Page): Promise<void> {
  const primaryNav = page.getByTestId('primary-nav');
  const trigger = page.getByTestId('products-mega-trigger');
  const panel = page.getByTestId('products-mega-panel');

  await expect(trigger).toBeVisible();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(panel).toBeHidden();
  await expect(panel).toHaveAttribute('aria-hidden', 'true');

  await expect(primaryNav.getByTestId('products-mega-panel')).toHaveCount(0);

  await trigger.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await expect(panel).toBeVisible();
  await expect(panel).toHaveAttribute('aria-hidden', 'false');
  expect(await panel.locator('a').count()).toBeGreaterThan(0);

  await page.keyboard.press('Escape');
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(panel).toBeHidden();

  await trigger.click();
  await expect(panel).toBeVisible();
  await page.locator('header.site-header .brand').click();
  await expect(panel).toBeHidden();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
}

async function assertTeaserGrid(page: Page, url: string): Promise<void> {
  await gotoWithRetry(page, url);
  const grid = page.getByTestId('teaser-grid');
  await expect(grid).toBeVisible();
  expect(await grid.locator('article.teaser-card').count()).toBeGreaterThan(0);
  expect(await grid.locator('a.teaser-card__link').count()).toBeGreaterThan(0);
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
    await assertDesktopMegaMenu(page);

    await expect(primaryNav.locator('a[href*="ueber-uns"], a[href*="about-us"]')).toHaveCount(0);

    await assertDrawerNavigation(page, 'de');
    await assertTeaserGrid(page, `${base}/de/produkte/`);
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
    await assertDesktopMegaMenu(page);

    await expect(primaryNav.locator('a[href*="ueber-uns"], a[href*="about-us"]')).toHaveCount(0);

    await assertDrawerNavigation(page, 'en');
    await assertTeaserGrid(page, `${base}/en/products/`);
  });
});
