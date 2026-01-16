import { test, expect } from '@playwright/test';

test.describe('Live navigation (Wissen)', () => {
  test('DE live navigation', async ({ page }) => {
    // IMPORTANT: no leading slash → relative to baseURL (/wissen/)
    await page.goto('de/', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 15000 });

    const productsLink = page.getByRole('link', { name: 'Produkte', exact: true });
    await expect(productsLink).toBeVisible({ timeout: 15000 });
    await productsLink.click();

    // Expect within /wissen/de/...
    await expect(page).toHaveURL(/\/wissen\/de\/produkte\/?/, { timeout: 15000 });

    await page.goto('de/', { waitUntil: 'domcontentloaded' });

    const faqLink = page.getByRole('link', { name: 'FAQ', exact: true });
    await expect(faqLink).toBeVisible({ timeout: 15000 });
    await faqLink.click();

    await expect(page).toHaveURL(/\/wissen\/de\/faq\/?/, { timeout: 15000 });
  });

  test('EN live navigation', async ({ page }) => {
    await page.goto('en/', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('header.site-header')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('footer.site-footer')).toBeVisible({ timeout: 15000 });

    const productsLink = page.getByRole('link', { name: 'Products', exact: true });
    await expect(productsLink).toBeVisible({ timeout: 15000 });
    await productsLink.click();

    await expect(page).toHaveURL(/\/wissen\/en\/products\/?/, { timeout: 15000 });

    await page.goto('en/', { waitUntil: 'domcontentloaded' });

    const faqLink = page.getByRole('link', { name: 'FAQ', exact: true });
    await expect(faqLink).toBeVisible({ timeout: 15000 });
    await faqLink.click();

    await expect(page).toHaveURL(/\/wissen\/en\/faq\/?/, { timeout: 15000 });
  });
});
