/**
 * The dashboard against the real FastAPI endpoints (#49, #50), not the mock. Skipped unless
 * E2E_API_URL is set, like tests/confirmation-api.spec.ts, whose setup it shares: migrate a
 * database, load the test catalogue, run the API with VALIO_SOURCE=snapshot on :8000, then
 *   E2E_API_URL=http://localhost:8000 pnpm exec playwright test tests/dashboard-api.spec.ts
 *
 * Each test makes its own order through FastAPI while the overview is open: a demo account
 * (a new company), a quote ("maito" 20 l and "arla" 5 l, 37,60 €, one flag), the
 * confirmation request, then the buyer's tick and confirm on the confirmation endpoints.
 * The card has to appear and change live, through the SSE stream and this app's
 * passthrough of /api/v1/public, and the order's chain has to verify in the browser.
 */
import { expect, request as playwrightRequest, test, type APIRequestContext } from '@playwright/test';

const API = process.env.E2E_API_URL;

test.skip(!API, 'E2E_API_URL is not set');
test.skip(({ isMobile }) => isMobile, 'The dashboard targets computers');

const LINES = [
	{ line_id: 'l1', text: 'maito', quantity: 20, unit: 'l', needed_by: '2026-11-16' },
	{ line_id: 'l2', text: 'arla', quantity: 5, unit: 'l', needed_by: '2026-11-16' }
];

interface Buyer {
	api: APIRequestContext;
	company: string;
}

async function newBuyer(): Promise<Buyer> {
	const api = await playwrightRequest.newContext({ baseURL: API });
	const phone = `+35840${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;
	const account = await api.post('/api/v1/demo/accounts', { data: { phone_e164: phone, exclusions: [], lang: 'en' } });
	expect(account.status()).toBe(201);
	return { api, company: (await account.json()).company_name };
}

/** Builds the quote and sends the link; returns the token from the buyer's inbox. */
async function sendQuote({ api }: Buyer): Promise<string> {
	const quote = await (await api.post('/api/v1/quotes', { data: { lines: LINES } })).json();
	expect(quote.decision).toBe('ready');
	expect((await api.post(`/api/v1/quotes/${quote.quote_id}/confirmation-request`)).status()).toBe(200);
	const [message] = await (await api.get('/api/v1/private/inbox')).json();
	return message.link.split('/c/')[1];
}

/** What the buyer does on the confirmation page: tick every flag, then confirm. */
async function confirm({ api }: Buyer, token: string): Promise<string> {
	const view = await (await api.get(`/api/v1/confirmations/${token}`)).json();
	const quote_hash = view.quote.quote_hash;
	for (const flag of view.flags) {
		const ack = await api.post(`/api/v1/confirmations/${token}/acknowledgements`, {
			data: { quote_hash, flag_key: flag.flag_key }
		});
		expect(ack.ok()).toBe(true);
	}
	const confirmed = await api.post(`/api/v1/confirmations/${token}/confirm`, { data: { quote_hash } });
	expect(confirmed.status()).toBe(200);
	return (await confirmed.json()).order_number;
}

test('shows a new order live, then its summary, flow and verified chain', async ({ page }) => {
	const buyer = await newBuyer();
	await page.goto('/dashboard');
	await expect(page.getByRole('heading', { name: 'Agent orders, live' })).toBeVisible();

	const company = page.getByTestId('company').filter({ has: page.getByRole('heading', { name: buyer.company }) });
	const card = company.getByTestId('order-card');
	const token = await sendQuote(buyer);
	// No reload: the card comes over the stream.
	await expect(card).toContainText('Waiting, ', { timeout: 15_000 });
	await expect(card).toContainText('20 l maito + 1 more');
	await expect(card).toContainText('1 flag: stock not confirmed');
	await expect(card.getByTestId('order-number')).toHaveCount(0);

	const orderNumber = await confirm(buyer, token);
	expect(orderNumber).toMatch(/^D-\d+$/);
	await expect(card).toContainText(/Confirmed \d\d:\d\d/, { timeout: 15_000 });
	await expect(card.getByTestId('order-number')).toHaveText(orderNumber);

	await card.click();
	await expect(page.getByRole('heading', { name: buyer.company })).toBeVisible();
	await expect(page.getByText(`Order ${orderNumber}`)).toBeVisible();
	await expect(page.getByText('by the buyer, after checking 1 flags')).toBeVisible();
	await expect(page.getByText('Quote not signed yet')).toBeVisible();
	await expect(page.getByTestId('ranked-not-available')).toBeVisible();
	await expect(page.getByRole('link', { name: /^Audit chain intact, \d+ events$/ })).toBeVisible();

	await page.getByRole('link', { name: 'Full flow', exact: true }).click();
	await expect(page.getByText('build_quote', { exact: true })).toBeVisible();
	await expect(page.getByText('request_confirmation', { exact: true })).toBeVisible();
	await expect(page.getByText('ready', { exact: true })).toBeVisible();

	await page.getByRole('link', { name: 'Audit log', exact: true }).click();
	const status = page.getByRole('main').getByRole('status');
	await expect(status).toContainText('Chain intact');
	await expect(status).toContainText('Quote not signed yet.');
	await page.getByRole('button', { name: 'Verify again' }).click();
	await expect(status).toContainText('Chain intact');

	const download = await page.request.get(await page.getByRole('link', { name: 'Download JSON' }).getAttribute('href') ?? '');
	expect(download.headers()['content-disposition']).toContain('attachment');
	const events = await download.json();
	expect(events.at(-1).type).toBe('order_confirmed');
	await buyer.api.dispose();
});

test('says an unknown order is not found', async ({ page }) => {
	const response = await page.goto('/dashboard/00000000-0000-0000-0000-000000000000');
	expect(response?.status()).toBe(404);
});
