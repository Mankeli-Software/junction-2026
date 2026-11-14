/**
 * The confirmation page against the real FastAPI endpoints (#47), not the fixture.
 * Skipped unless E2E_API_URL is set, so CI keeps running the fixture tests only.
 *
 * Each test makes its own order through FastAPI, as an agent and its buyer would: a demo
 * account, a quote from the fixture catalogue and the recorded Valio snapshots, the
 * confirmation request, and the link from the account's inbox. "maito" 20 l is Valio Arki
 * semi skimmed milk (stock not confirmed, so one flag to tick), "arla" 5 l is Arla fat free
 * milk; 37,60 € in all.
 *
 * Run: start Postgres, migrate, run the API with VALIO_SOURCE=snapshot on :8000, then
 *   E2E_API_URL=http://localhost:8000 pnpm exec playwright test tests/confirmation-api.spec.ts
 */
import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';

const API = process.env.E2E_API_URL;

test.skip(!API, 'E2E_API_URL is not set');

const LINES = [
	{ line_id: 'l1', text: 'maito', quantity: 20, unit: 'l', needed_by: '2026-11-16' },
	{ line_id: 'l2', text: 'arla', quantity: 5, unit: 'l', needed_by: '2026-11-16' }
];

/** A new buyer's order, sent for confirmation; returns the token from their inbox. */
async function orderToken(): Promise<string> {
	const api = await playwrightRequest.newContext({ baseURL: API });
	const phone = `+35840${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;
	const account = await api.post('/api/v1/demo/accounts', {
		data: { phone_e164: phone, exclusions: [], lang: 'en' }
	});
	expect(account.status()).toBe(201);
	const quote = await (await api.post('/api/v1/quotes', { data: { lines: LINES } })).json();
	expect(quote.decision).toBe('ready');
	const sent = await api.post(`/api/v1/quotes/${quote.quote_id}/confirmation-request`);
	expect(sent.status()).toBe(200);
	const [message] = await (await api.get('/api/v1/private/inbox')).json();
	await api.dispose();
	return message.link.split('/c/')[1];
}

const flag = (page: Page, title: RegExp) => page.getByTestId('flag').filter({ hasText: title });
const confirmButton = (page: Page) => page.getByRole('button', { name: /confirm/i });

test('confirms an order with one acknowledgement and one edit', async ({ page }) => {
	await page.goto(`/c/${await orderToken()}`);

	await expect(page.getByRole('heading', { name: 'Your order' })).toBeVisible();
	await expect(page.getByTestId('flag-count')).toHaveText('0 of 1 done');
	await expect(page.getByTestId('total')).toHaveText(/37,60\s€/);
	await expect(confirmButton(page)).toBeDisabled();

	await flag(page, /Stock not confirmed/).getByRole('button', { name: 'Got it' }).click();
	await expect(page.getByTestId('flag-count')).toHaveText('1 of 1 done');

	// Edit: one more carton of the Arla milk. This makes a new quote.
	await page.getByTestId('line').filter({ hasText: 'Arla fat free' }).getByRole('link', { name: 'Why this product' }).click();
	const sheet = page.getByTestId('line-sheet');
	await expect(sheet.getByTestId('sheet-quantity')).toHaveText('5 piece');
	await sheet.getByRole('button', { name: 'More' }).click();
	await expect(sheet.getByTestId('sheet-quantity')).toHaveText('6 piece');
	await sheet.getByRole('link', { name: 'Close' }).click();
	await expect(page.getByTestId('total-changed')).toHaveText(/37,60\s€ → 40,52\s€/);
	await expect(page.getByTestId('flag-count')).toHaveText('1 of 1 done');

	await expect(confirmButton(page)).toBeEnabled();
	await confirmButton(page).click();

	await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
	await expect(page.getByTestId('order-number')).toHaveText(/Order D-\d+, confirmed \d\d:\d\d/);
	await expect(page.getByText('You checked 1 flagged item before confirming.')).toBeVisible();

	// The link stays readable as a receipt.
	await page.reload();
	await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
});

test('refuses an action from a stale tab', async ({ browser }) => {
	const token = await orderToken();
	const context = await browser.newContext();
	const first = await context.newPage();
	const second = await context.newPage();
	await first.goto(`/c/${token}`);
	await second.goto(`/c/${token}`);

	await first.getByTestId('line').filter({ hasText: 'Arla fat free' }).getByRole('link', { name: 'Why this product' }).click();
	await first.getByTestId('line-sheet').getByRole('button', { name: 'More' }).click();
	await expect(first.getByTestId('total')).toHaveText(/40,52\s€/);

	await flag(second, /Stock not confirmed/).getByRole('button', { name: 'Got it' }).click();
	await expect(second.getByRole('alert')).toHaveText('The order changed in another window. This is the latest version.');
	await expect(second.getByTestId('total')).toHaveText(/40,52\s€/);
	await context.close();
});

test('cancels after asking once', async ({ page }) => {
	await page.goto(`/c/${await orderToken()}`);
	await page.getByRole('link', { name: 'Cancel order' }).click();
	await page.getByRole('button', { name: 'Yes, cancel' }).click();
	await expect(page.getByRole('heading', { name: 'Order cancelled' })).toBeVisible();
});

test('says an unknown link is not valid', async ({ page }) => {
	const response = await page.goto('/c/not-a-real-token');
	expect(response?.status()).toBe(404);
	await expect(page.getByRole('heading', { name: 'This link is not valid.' })).toBeVisible();
});

test.describe('without JavaScript', () => {
	test.use({ javaScriptEnabled: false });

	test('acknowledges and confirms with plain forms', async ({ page }) => {
		await page.goto(`/c/${await orderToken()}`);
		await flag(page, /Stock not confirmed/).getByRole('button', { name: 'Got it' }).click();
		await expect(page.getByTestId('flag-count')).toHaveText('1 of 1 done');
		await confirmButton(page).click();
		await expect(page.getByRole('heading', { name: 'Order received' })).toBeVisible();
	});
});
