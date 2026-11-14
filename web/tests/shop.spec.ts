/**
 * The webshop (#56) with a WebMCP shim (tests/support/webmcp-shim.ts) in place of a
 * browser agent. The number entry and the session are the demo fixture
 * (DEMO_SOURCE=fixture); the agent tools' REST twins are answered here with
 * `page.route`, so no FastAPI is needed.
 */
import { readFileSync } from 'node:fs';
import { expect, test, type Page, type Route } from '@playwright/test';
import { callTool, installWebMcpShim, registeredTools } from './support/webmcp-shim';

const AGENT_TOOLS = JSON.parse(readFileSync(new URL('../src/lib/generated/agent-tools.json', import.meta.url), 'utf8')) as {
	name: string;
	description: string;
	inputSchema: Record<string, unknown>;
}[];

const LINES = [{ line_id: 'l1', text: 'laktoositon maito', quantity: 20, unit: 'l', needed_by: '2026-11-16' }];

const QUOTE = {
	quote_id: 'q-shop-1',
	version: 1,
	parent_quote_id: null,
	status: 'ready',
	decision: 'ready',
	lines: [{ line_id: 'l1', product_id: '464073' }],
	total_cents: 3720,
	speak: { en: 'Twenty litres of lactose-free milk.', fi: 'Kaksikymmentä litraa laktoositonta maitoa.' }
};

const CONFIRMATION = { sent_to_masked: '+358 40 *** **12', delivery_status: 'off', inbox: true };

function number(): string {
	return `40 ${String(Math.floor(Math.random() * 1e7)).padStart(7, '0')}`;
}

async function signIn(page: Page, phone = number()) {
	await page.getByLabel('Your real phone number').fill(phone);
	await page.getByRole('button', { name: 'Continue' }).click();
	await expect(page.getByTestId('company')).toHaveText(/ Oy$/);
}

/** Answers the REST twins the way FastAPI would, and records what the page sent. */
async function fakeTwins(page: Page) {
	const requests: { method: string; url: string; body: unknown; cookie: string }[] = [];
	const record = async (route: Route) => {
		const request = route.request();
		const headers = await request.allHeaders();
		requests.push({
			method: request.method(),
			url: new URL(request.url()).pathname + new URL(request.url()).search,
			body: request.postData() ? request.postDataJSON() : null,
			cookie: headers.cookie ?? ''
		});
	};
	await page.route('**/api/v1/quotes', async (route) => {
		await record(route);
		await route.fulfill({ json: QUOTE });
	});
	await page.route('**/api/v1/quotes/*/confirmation-request', async (route) => {
		await record(route);
		await route.fulfill({ json: CONFIRMATION });
	});
	await page.route('**/api/v1/customer-context', async (route) => {
		await record(route);
		await route.fulfill({ status: 401, json: { detail: 'Not signed in' } });
	});
	return requests;
}

test('the page registers exactly the agent tools, as /mcp lists them', async ({ page }) => {
	await installWebMcpShim(page);
	await page.goto('/shop');
	await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');
	expect(await registeredTools(page)).toEqual(AGENT_TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })));
	const names = (await registeredTools(page)).map((tool) => tool.name);
	for (const forbidden of ['confirm', 'confirm_order', 'cancel', 'cancel_order', 'get_inbox', 'read_inbox', 'edit_quote']) {
		expect(names).not.toContain(forbidden);
	}
	await expect(page.getByText('10 ordering tools are ready')).toBeVisible();
});

test('the tools fall back to navigator.modelContext', async ({ page }) => {
	await installWebMcpShim(page, 'navigator');
	await page.goto('/shop');
	await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');
	expect((await registeredTools(page)).map((tool) => tool.name)).toEqual(AGENT_TOOLS.map((tool) => tool.name));
});

test('without a browser agent, the MCP-B runtime serves the tools for the extension', async ({ page }) => {
	// No shim: plain Chromium has no model context, so @mcp-b/global installs its polyfill (#93).
	await page.goto('/shop');
	await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');
	const names = await page.evaluate(async () => {
		const context = (document as unknown as { modelContext: { getTools(): Promise<{ name: string }[]> } }).modelContext;
		return (await context.getTools()).map((tool) => tool.name);
	});
	expect(names.sort()).toEqual(AGENT_TOOLS.map((tool) => tool.name).sort());
});

test('static products with pack size and category, no prices', async ({ page }) => {
	await page.goto('/shop');
	const products = page.getByTestId('product');
	await expect(products).toHaveCount(12);
	await expect(products.first()).toContainText('Valio whole milk 1 l lactose free UHT');
	await expect(products.first()).toContainText('Milk and sour milk drinks');
	await expect(products.first()).toContainText('Sold by the piece');
	await expect(page.locator('main')).not.toContainText('€');
	await page.getByRole('button', { name: 'Butter', exact: true }).click();
	await expect(products).toHaveCount(1);
	await expect(products.first()).toContainText('Valio butter 500 g salted');
});

test('number entry: checks the number, signs in like the phone, keeps it on reload', async ({ page }) => {
	await page.goto('/shop');
	await expect(page.getByRole('heading', { name: 'Who is ordering?' })).toBeVisible();
	await expect(page.getByText('public demo dashboard', { exact: false })).toBeVisible();
	await expect(page.getByText('No real order is placed.', { exact: false })).toBeVisible();

	await page.getByLabel('Your real phone number').fill('12');
	await page.getByRole('button', { name: 'Continue' }).click();
	await expect(page.getByRole('alert')).toContainText('Check the number');

	await page.getByLabel('Your real phone number').fill('40 765 4312');
	await page.getByTestId('identity').getByRole('button', { name: 'Milk', exact: true }).click();
	await page.getByRole('button', { name: 'Continue' }).click();
	await expect(page.getByTestId('company')).toHaveText(/ Oy$/);
	await expect(page.getByTestId('phone-masked')).toHaveText('+358 40 *** **12');
	const company = await page.getByTestId('company').textContent();

	await page.reload();
	await expect(page.getByTestId('company')).toHaveText(company!);

	// The demo phone in this tab opens on Contacts with the same account.
	await page.goto('/phone');
	await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible();
	await expect(page.getByTestId('company')).toHaveText(company!);
	await expect(page.getByTestId('kitchen')).toHaveText('Avoids milk');
});

test('build_quote and request_confirmation through WebMCP, with the session cookie', async ({ page }) => {
	await installWebMcpShim(page);
	const requests = await fakeTwins(page);
	await page.goto('/shop');
	await signIn(page);
	await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');

	const quote = await callTool(page, 'build_quote', { lines: LINES });
	expect(quote.isError).toBeFalsy();
	expect(quote.structuredContent).toEqual(QUOTE);
	expect(JSON.parse(quote.content[0].text)).toEqual(QUOTE);
	await expect(page.getByTestId('latest-quote')).toContainText(/1 line, 37,20/);
	await expect(page.getByTestId('latest-quote')).toContainText('Ready to send for confirmation');

	const sent = await callTool(page, 'request_confirmation', { quote_id: 'q-shop-1' });
	expect(sent.isError).toBeFalsy();
	expect(sent.structuredContent).toEqual(CONFIRMATION);

	expect(requests.map(({ method, url, body }) => ({ method, url, body }))).toEqual([
		{ method: 'POST', url: '/api/v1/quotes', body: { lines: LINES } },
		{ method: 'POST', url: '/api/v1/quotes/q-shop-1/confirmation-request', body: null }
	]);
	for (const request of requests) expect(request.cookie).toMatch(/simo_session=/);

	const notice = page.getByTestId('confirmation-notice');
	await expect(notice).toContainText('Your confirmation link is in your demo phone');
	await expect(notice.getByRole('link', { name: 'Open the demo phone' })).toHaveAttribute('href', '/phone');
});

test('no confirmation link anywhere in the shop', async ({ page }) => {
	await installWebMcpShim(page);
	await fakeTwins(page);
	await page.goto('/shop');
	await signIn(page);
	await callTool(page, 'build_quote', { lines: LINES });
	const sent = await callTool(page, 'request_confirmation', { quote_id: 'q-shop-1' });
	await expect(page.getByTestId('confirmation-notice')).toBeVisible();

	expect(JSON.stringify(sent)).not.toMatch(/\/c\/|https?:/);
	await expect(page.locator('a[href*="/c/"]')).toHaveCount(0);
	const hrefs = await page.locator('a[href]').evaluateAll((links) => links.map((a) => a.getAttribute('href')));
	expect(hrefs.every((href) => href === '/phone' || href!.startsWith('?lang='))).toBe(true);
	expect(await page.locator('body').innerText()).not.toMatch(/\/c\/|fx-/);
});

test('a tool without a session tells the agent to ask for the number', async ({ page }) => {
	await installWebMcpShim(page);
	await fakeTwins(page);
	await page.goto('/shop');
	await expect(page.getByTestId('tools')).toHaveAttribute('data-state', 'ready');
	const result = await callTool(page, 'get_customer_context', {});
	expect(result.isError).toBe(true);
	expect(result.content[0].text).toMatch(/phone number on this page/);
});

test.describe('Finnish browser', () => {
	test.use({ locale: 'fi-FI' });

	test('the shop opens in Finnish, and the toggle switches to English', async ({ page }) => {
		await page.goto('/shop');
		await expect(page.getByRole('heading', { level: 1 })).toHaveText('Valion tuotteet ammattikeittiöille');
		await expect(page.getByRole('heading', { name: 'Kuka tilaa?' })).toBeVisible();
		await expect(page.getByTestId('product').first()).toContainText('Valio täysmaito 1 l laktoositon UHT');

		await page.getByRole('link', { name: 'EN', exact: true }).click();
		await expect(page).toHaveURL(/\?lang=en$/);
		await expect(page.getByRole('heading', { level: 1 })).toHaveText('Valio products for professional kitchens');
	});

	test('the pointer to the demo phone keeps Finnish', async ({ page }) => {
		await installWebMcpShim(page);
		await fakeTwins(page);
		await page.goto('/shop');
		await page.getByLabel('Oikea puhelinnumerosi').fill(number());
		await page.getByRole('button', { name: 'Jatka' }).click();
		await expect(page.getByTestId('company')).toHaveText(/ Oy$/);
		await callTool(page, 'request_confirmation', { quote_id: 'q-shop-1' });
		const notice = page.getByTestId('confirmation-notice');
		await expect(notice).toContainText('Vahvistuslinkkisi on demopuhelimessasi');
		await expect(notice.getByRole('link')).toHaveAttribute('href', '/phone?lang=fi');
	});
});

test.describe('English browser', () => {
	test.use({ locale: 'en-US' });

	test('the shop opens in English, and the toggle switches to Finnish', async ({ page }) => {
		await page.goto('/shop');
		await expect(page.getByRole('heading', { level: 1 })).toHaveText('Valio products for professional kitchens');
		await page.getByRole('link', { name: 'FI', exact: true }).click();
		await expect(page).toHaveURL(/\?lang=fi$/);
		await expect(page.getByRole('heading', { level: 1 })).toHaveText('Valion tuotteet ammattikeittiöille');
	});
});
