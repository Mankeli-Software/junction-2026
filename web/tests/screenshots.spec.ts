/**
 * Screenshots of the confirmation page for pull requests and reviews, saved to
 * docs/screenshots/confirmation-page/. Skipped in normal test runs; regenerate with
 *
 *   SCREENSHOTS=1 pnpm exec playwright test screenshots --project=phone
 *
 * The confirm bar is sticky on a real phone; for full-page images it is pinned to
 * the end of the page so it doesn't land in the middle of the picture.
 */
import { expect, test, type Page } from '@playwright/test';

const OUT = '../docs/screenshots/confirmation-page';

test.skip(!process.env.SCREENSHOTS, 'Set SCREENSHOTS=1 to take screenshots');

const token = (scenario: string) => `fx-${scenario}-shot${Math.random().toString(36).slice(2, 8)}`;

async function fullPage(page: Page, name: string) {
	await page.mouse.move(0, 0);
	await page.addStyleTag({ content: '.bar { position: static !important; }' });
	await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

test('confirmation page screenshots', async ({ page }) => {
	const ready = token('ready');

	await page.goto(`/c/${ready}`);
	await expect(page.getByTestId('flag-count')).toHaveText('1 of 3 done');
	await fullPage(page, '1-check-these-first');

	await page.goto(`/c/${ready}?line=l1`);
	await expect(page.getByTestId('line-sheet')).toBeVisible();
	await page.screenshot({ path: `${OUT}/2-why-this-product.png` });

	await page.goto(`/c/${ready}`);
	await page.getByTestId('flag').filter({ hasText: /No allergen info/ }).getByRole('button', { name: 'Got it' }).click();
	await page.getByTestId('flag').filter({ hasText: /Rounded up/ }).getByRole('button', { name: /Exactly 20 l/ }).click();
	await expect(page.getByTestId('total-changed')).toBeVisible();
	await fullPage(page, '3-after-an-edit');

	await page.getByRole('button', { name: /confirm/i }).click();
	await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
	await page.screenshot({ path: `${OUT}/4-order-received.png`, fullPage: true });

	const requote = token('requote');
	await page.goto(`/c/${requote}`);
	await page.getByTestId('flag').filter({ hasText: /No allergen info/ }).getByRole('button', { name: 'Got it' }).click();
	await page.getByTestId('flag').filter({ hasText: /Rounded up/ }).getByRole('button', { name: /Keep 24 l/ }).click();
	await page.getByRole('button', { name: /confirm/i }).click();
	await expect(page.getByTestId('requote')).toBeVisible();
	await fullPage(page, '5-stock-changed');

	await page.goto(`/c/${token('fi')}`);
	await expect(page.getByRole('heading', { name: 'Tilauksesi' })).toBeVisible();
	await fullPage(page, '6-finnish');
});
