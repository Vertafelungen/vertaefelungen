import { expect, test } from '@playwright/test';

async function logClickInterception(page: import('@playwright/test').Page, locator: import('@playwright/test').Locator, label: string) {
  const box = await locator.boundingBox();
  if (!box) {
    console.log(`[click-debug] ${label}: bounding box unavailable`);
    return;
  }

  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const info = await page.evaluate(({ x, y }) => {
    const target = document.elementFromPoint(x, y) as HTMLElement | null;
    if (!target) {
      return { found: false };
    }
    const style = window.getComputedStyle(target);
    return {
      found: true,
      tagName: target.tagName,
      pointerEvents: style.pointerEvents,
      zIndex: style.zIndex,
      outerHTML: target.outerHTML.slice(0, 500),
    };
  }, point);

  console.log(`[click-debug] ${label}:`, info);
}

async function clickAndVerify(page: import('@playwright/test').Page, locator: import('@playwright/test').Locator, urlPattern: RegExp, label: string) {
  try {
    const [response] = await Promise.all([
      page.waitForNavigation({ url: urlPattern }),
      locator.click(),
    ]);

    await expect(page).toHaveURL(urlPattern);
    expect(response, `${label} navigation returned no response`).not.toBeNull();
    expect(response?.ok(), `${label} navigation response not OK`).toBeTruthy();
  } catch (error) {
    await logClickInterception(page, locator, label);
    throw error;
  }
}

test('DE live navigation', async ({ page }) => {
  await page.goto('/de/');

  await expect(page.locator('header.site-header')).toBeVisible();
  await expect(page.locator('footer.site-footer')).toBeVisible();

  const productsLink = page.getByRole('link', { name: 'Produkte', exact: true });
  await expect(productsLink).toBeVisible();
  await clickAndVerify(page, productsLink, /\/de\/produkte\/?/, 'Produkte');

  await page.goto('/de/');
  const faqLink = page.getByRole('link', { name: 'FAQ', exact: true });
  await expect(faqLink).toBeVisible();
  await clickAndVerify(page, faqLink, /\/de\/faq\/?/, 'FAQ');
});

test('EN live navigation', async ({ page }) => {
  await page.goto('/en/');

  await expect(page.locator('header.site-header')).toBeVisible();
  await expect(page.locator('footer.site-footer')).toBeVisible();

  const productsLink = page.getByRole('link', { name: 'Products', exact: true });
  await expect(productsLink).toBeVisible();
  await clickAndVerify(page, productsLink, /\/en\/products\/?/, 'Products');

  await page.goto('/en/');
  const faqLink = page.getByRole('link', { name: 'FAQ', exact: true });
  await expect(faqLink).toBeVisible();
  await clickAndVerify(page, faqLink, /\/en\/faq\/?/, 'FAQ');
});
