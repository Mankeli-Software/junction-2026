/**
 * The confirmation page /c/[token] against the fixture (issue #55). Each test uses
 * its own token, so tests don't share quote state. Token prefixes pick the fixture
 * scenario: fx-ready, fx-requote, ...
 */
import { expect, test, type Page } from '@playwright/test';

function token(scenario: string): string {
	return `fx-${scenario}-${Math.random().toString(36).slice(2, 10)}`;
}

const flag = (page: Page, title: RegExp) => page.getByTestId('flag').filter({ hasText: title });
const confirmButton = (page: Page) => page.getByRole('button', { name: /confirm/i });

test('confirms an order with one acknowledgement and one edit', async ({ page }) => {
	await page.goto(`/c/${token('ready')}`);

	await expect(page.getByRole('heading', { name: 'Your order' })).toBeVisible();
	await expect(page.getByTestId('flag-count')).toHaveText('1 of 3 done');
	await expect(page.getByTestId('total')).toHaveText(/128,40\s€/);
	await expect(confirmButton(page)).toBeDisabled();

	// Acknowledge: the missing allergen information.
	await flag(page, /No allergen info/).getByRole('button', { name: 'Got it' }).click();
	await expect(page.getByTestId('flag-count')).toHaveText('2 of 3 done');

	// Edit: take the exact 20 l instead of rounding up to 24 l. This makes a new quote.
	await flag(page, /Rounded up/).getByRole('button', { name: /Exactly 20 l/ }).click();
	await expect(page.getByTestId('total-changed')).toHaveText(/128,40\s€ → 122,80\s€/);
	await expect(page.getByTestId('total')).toHaveText(/122,80\s€/);
	await expect(page.getByTestId('flag-count')).toHaveText('2 of 2 done');
	await expect(page.getByTestId('line').filter({ hasText: 'Oat drink 2,5 l' })).toContainText('Changed');

	await expect(confirmButton(page)).toBeEnabled();
	await confirmButton(page).click();

	await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
	await expect(page.getByTestId('order-number')).toHaveText(/Order D-\d+, confirmed \d\d:\d\d/);
	await expect(page.getByText('You checked 2 flagged items before confirming.')).toBeVisible();
	await expect(page.getByText('No real order was sent.', { exact: false })).toBeVisible();

	// The link stays readable as a receipt.
	await page.reload();
	await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
});

test('changes the amount in the line sheet', async ({ page }) => {
	await page.goto(`/c/${token('ready')}`);
	await page
		.getByTestId('line')
		.filter({ hasText: 'Beef mince' })
		.getByRole('link', { name: 'Why this product' })
		.click();

	const sheet = page.getByTestId('line-sheet');
	await expect(sheet.getByRole('heading', { name: 'Why this one' })).toBeVisible();
	await expect(sheet).toContainText('14');
	await expect(sheet.getByTestId('sheet-quantity')).toHaveText('2 pcs');

	await sheet.getByRole('button', { name: 'More' }).click();
	await expect(sheet.getByTestId('sheet-quantity')).toHaveText('3 pcs');
	await expect(page.getByTestId('total')).toHaveText(/149,35\s€/);

	await sheet.getByRole('link', { name: 'Close' }).click();
	await expect(sheet).toBeHidden();
	await expect(page.getByTestId('line').filter({ hasText: 'Beef mince' })).toContainText('3 pcs = 7,5 kg');
});

test('shows the updated order when stock changed before confirming', async ({ page }) => {
	await page.goto(`/c/${token('requote')}`);
	await flag(page, /No allergen info/).getByRole('button', { name: 'Got it' }).click();
	await flag(page, /Rounded up/).getByRole('button', { name: /Keep 24 l/ }).click();
	await expect(page.getByTestId('flag-count')).toHaveText('3 of 3 done');

	await confirmButton(page).click();

	await expect(page.getByTestId('requote')).toHaveText('Stock changed since the quote. Here is the updated order.');
	const substitute = flag(page, /Substitute/);
	await expect(substitute).toContainText('New');
	await expect(confirmButton(page)).toBeDisabled();

	await substitute.getByRole('button', { name: 'Got it' }).click();
	await confirmButton(page).click();
	await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
});

test('refuses an action from a stale tab', async ({ browser }) => {
	const shared = token('ready');
	const context = await browser.newContext();
	const first = await context.newPage();
	const second = await context.newPage();
	await first.goto(`/c/${shared}`);
	await second.goto(`/c/${shared}`);

	await flag(first, /Rounded up/).getByRole('button', { name: /Exactly 20 l/ }).click();
	await expect(first.getByTestId('total')).toHaveText(/122,80\s€/);

	// The second tab still shows the old quote; its action must not go through blindly.
	await flag(second, /No allergen info/).getByRole('button', { name: 'Got it' }).click();
	await expect(second.getByRole('alert')).toHaveText('The order changed in another window. This is the latest version.');
	await expect(second.getByTestId('total')).toHaveText(/122,80\s€/);
	await expect(second.getByTestId('flag-count')).toHaveText('1 of 2 done');
	await context.close();
});

test('cancels after asking once', async ({ page }) => {
	await page.goto(`/c/${token('ready')}`);
	await page.getByRole('link', { name: 'Cancel order' }).click();
	await expect(page.getByText('Cancel this order? Nothing will be ordered.')).toBeVisible();
	await page.getByRole('button', { name: 'Yes, cancel' }).click();
	await expect(page.getByRole('heading', { name: 'Order cancelled' })).toBeVisible();
});

test('switches language', async ({ page }) => {
	await page.goto(`/c/${token('ready')}`);
	await page.getByRole('link', { name: 'FI' }).click();
	await expect(page.getByRole('heading', { name: 'Tilauksesi' })).toBeVisible();
	await expect(page.getByText('Hassu Hauki Oy, puhelu klo 10.02')).toBeVisible();
	await expect(page.getByTestId('flag-count')).toHaveText('1/3 tarkistettu');
});

test('starts in the language of the call', async ({ page }) => {
	await page.goto(`/c/${token('fi')}`);
	await expect(page.getByRole('heading', { name: 'Tilauksesi' })).toBeVisible();
	await expect(page.getByTestId('total')).toHaveText(/128,40\s€/);
});

test('says an unknown link is not valid', async ({ page }) => {
	const response = await page.goto('/c/not-a-real-token');
	expect(response?.status()).toBe(404);
	await expect(page.getByRole('heading', { name: 'This link is not valid.' })).toBeVisible();
});

test('sends no referrer to other sites and is not cached', async ({ page }) => {
	const response = await page.goto(`/c/${token('ready')}`);
	expect(response?.headers()['referrer-policy']).toBe('same-origin');
	expect(response?.headers()['cache-control']).toBe('no-store');
});

test.describe('without JavaScript', () => {
	test.use({ javaScriptEnabled: false });

	test('acknowledges and confirms with plain forms', async ({ page }) => {
		await page.goto(`/c/${token('ready')}`);
		await flag(page, /No allergen info/).getByRole('button', { name: 'Got it' }).click();
		await flag(page, /Rounded up/).getByRole('button', { name: /Keep 24 l/ }).click();
		await expect(page.getByTestId('flag-count')).toHaveText('3 of 3 done');
		await confirmButton(page).click();
		await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
	});
});
